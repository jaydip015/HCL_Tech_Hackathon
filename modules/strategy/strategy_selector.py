"""Policy-based strategy selection with suppression rules (Person 3).

segment -> objective, tone, template, reminder stage, offer; then suppression:
  NO_CONSENT (marketing), RECENT_CONTACT (cooldown), DUPLICATE, OVERDUE => never promotional,
  DATA / MANUAL_REVIEW => escalate. Also builds the verified `facts` the writer may use.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.schemas.models import (BlockReason, ContactRecord, CustomerProfile, FailureCategory, SegmentResult,
                                    Strategy)
from backend.services.formatting import fmt_date, fmt_money
from config import Settings
from modules.offers.offer_eligibility import check_offer, evaluate_catalog, select_offer
from modules.offers.offer_repository import OfferRepository


def reminder_stage_for(days_overdue: int, stages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for st in stages:
        lo, hi = st["min_days"], st.get("max_days")
        if days_overdue >= lo and (hi is None or days_overdue <= hi):
            return st
    return None


def last_contact_days(profile: CustomerProfile, history: list[ContactRecord], as_of: date) -> int | None:
    candidates = []
    if profile.last_contacted_date:
        candidates.append((as_of - profile.last_contacted_date).days)
    for h in history:
        candidates.append((as_of - h.sent_at.date()).days)
    return min(candidates) if candidates else None


class StrategySelector:
    def __init__(self, settings: Settings, offers: OfferRepository):
        self.settings = settings
        self.offers = offers

    def build_facts(self, profile: CustomerProfile, strategy: Strategy) -> dict[str, Any]:
        comm = self.settings.communication
        sym = comm["currency"]["symbol"]
        facts: dict[str, Any] = {
            "first_name": profile.first_name,
            "company_name": comm["support"]["company_name"],
            "support_phone": comm["support"]["phone"],
            "support_email": comm["support"]["email"],
            "dispute_url": comm["support"]["dispute_url"],
        }
        if profile.tenure_months is not None:
            facts["tenure_months"] = profile.tenure_months
            if profile.tenure_months >= 12:
                facts["tenure_years"] = profile.tenure_months // 12
        if profile.contract_type:
            facts["contract_type"] = profile.contract_type
        if strategy.objective == "REMIND":
            facts["amount_due"] = fmt_money(profile.amount_due, sym)
            facts["due_date"] = fmt_date(profile.bill_due_date)
            facts["days_overdue"] = profile.days_overdue
            facts["reminder_stage"] = strategy.reminder_stage
        if strategy.offer:
            o = strategy.offer
            facts.update({"offer_id": o.offer_id, "offer_name": o.name, "offer_value": o.value,
                          "offer_description": o.description, "offer_terms": o.terms,
                          "offer_expiry": fmt_date(o.expiry_date)})
        allowed = set(self.settings.privacy.get("llm_context_allowed_fields", []))
        return {k: v for k, v in facts.items() if k in allowed}

    def select(self, profile: CustomerProfile, segment: SegmentResult, history: list[ContactRecord] | None = None,
               forced_offer_id: str | None = None) -> Strategy:
        history = history or []
        s = self.settings
        comm, rem = s.communication, s.reminders
        as_of = s.as_of_date
        st = Strategy(customer_id=profile.customer_id, primary_segment=segment.primary_segment,
                      policy_version=s.policy_version)

        def block(code: str, cat: FailureCategory, detail: str, ref: str | None = None) -> None:
            st.blocked = True
            st.block_reasons.append(BlockReason(code=code, category=cat, detail=detail, policy_ref=ref))

        # Escalations from segmentation (missing/contradictory data, no rule, low confidence)
        if segment.status != "CLASSIFIED":
            for reason in segment.manual_review_reasons or ["MANUAL_REVIEW"]:
                cat = FailureCategory.DATA if reason.startswith(("DATA_ISSUE", "MISSING_EVIDENCE")) else FailureCategory.POLICY
                block("MANUAL_REVIEW", cat, reason, "Dispute and Support Escalation Policy §3")
            return st

        primary = segment.primary_segment
        cfg = comm["strategy_map"][primary]
        st.policy_refs.append(cfg.get("policy_ref", ""))
        days_contact = last_contact_days(profile, history, as_of)

        if primary == "OVERDUE":
            stage = reminder_stage_for(profile.days_overdue, rem["stages"])
            if stage is None:
                block("NO_STAGE", FailureCategory.POLICY, f"No reminder stage for {profile.days_overdue} days overdue.")
                return st
            st.objective, st.tone, st.template_id = "REMIND", stage["tone"], stage["template"]
            st.reminder_stage, st.is_marketing = stage["stage"], False
            st.policy_refs.append(f"Payment Reminder Policy §2 (stage {stage['stage']})")
            st.notes.append(f"{profile.days_overdue} days overdue -> stage {stage['stage']} ({stage['label']}).")
            if segment.secondary_segments:
                st.notes.append(f"Secondary segments {segment.secondary_segments} ignored: reminders take priority and never carry offers.")
            cooldown = comm["frequency"]["reminder_cooldown_days"]
            if days_contact is not None and days_contact < cooldown:
                block("RECENT_CONTACT", FailureCategory.POLICY,
                      f"Last contact {days_contact} day(s) ago; reminder cooldown is {cooldown} days.",
                      "Communication Frequency Policy §1")
            st.facts = self.build_facts(profile, st)
            return st

        # Marketing strategies
        st.objective, st.tone, st.template_id = cfg["objective"], cfg["tone"], cfg["template"]
        st.is_marketing = st.objective in comm.get("marketing_objectives", [])
        if st.is_marketing and profile.marketing_consent is not True:
            block("NO_CONSENT", FailureCategory.POLICY,
                  "Customer has no verified marketing consent; promotional communication is blocked.",
                  "Marketing Consent Policy §3")
        cooldown = comm["frequency"]["marketing_cooldown_days"]
        if days_contact is not None and days_contact < cooldown:
            block("RECENT_CONTACT", FailureCategory.POLICY,
                  f"Last contact {days_contact} day(s) ago; marketing cooldown is {cooldown} days.",
                  "Communication Frequency Policy §1")
        dup_window = comm["frequency"]["duplicate_window_days"]
        for h in history:
            if h.template_id == st.template_id and (as_of - h.sent_at.date()).days < dup_window:
                block("DUPLICATE_OUTREACH", FailureCategory.POLICY,
                      f"Template {st.template_id} already sent on {h.sent_at.date()} (within {dup_window} days).",
                      "Communication Frequency Policy §2")
                break

        # Offers: evaluate whole catalog so the UI can explain every accept/reject
        offers = self.offers.all()
        st.offer_decisions = evaluate_catalog(offers, profile, segment, as_of, self.offers.rules)
        offer_mode = cfg.get("offer", "OPTIONAL")
        chosen = None
        if forced_offer_id:
            forced = self.offers.get(forced_offer_id)
            if forced is None:
                st.notes.append(f"Requested offer {forced_offer_id} does not exist in the approved catalog; ignored.")
            else:
                dec = check_offer(forced, profile, segment, as_of, self.offers.rules)
                if dec.eligible:
                    chosen = forced
                else:
                    st.notes.append(f"Assigned offer {forced_offer_id} rejected ({'; '.join(dec.reasons)}); strategy recomputed.")
        if chosen is None and offer_mode != "NEVER" and not st.blocked:
            chosen = select_offer(offers, st.offer_decisions)
        if chosen is None and offer_mode == "REQUIRED" and not st.blocked:
            fb = comm.get("no_offer_fallback", {}).get(primary)
            if fb:
                st.objective, st.tone, st.template_id = fb["objective"], fb["tone"], fb["template"]
                st.notes.append(f"No eligible {primary} offer; fell back to {fb['objective']} without an offer.")
            else:
                block("NO_ELIGIBLE_OFFER", FailureCategory.POLICY, "Strategy requires an offer but none is eligible.")
        st.offer = chosen if not st.blocked else None
        if st.offer:
            st.policy_refs.append("Offer Eligibility Policy §2")
        st.facts = self.build_facts(profile, st)
        return st
