"""Customer overview with policy proof (Person 2).

For ONE customer: which category (segment) they belong to, every rule check with the
customer's actual value, and the exact policy section that defines the rule, quoted from the
knowledge base. Everything here is deterministic: the segmentation engine and strategy
selector are the authority, and this service only lays out their recorded evidence next to
the policy text. No LLM is involved, so the proof cannot be paraphrased or invented.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from backend.schemas.models import (ConditionCheck, CustomerOverview, OverviewReason, PolicyQuote,
                                    SegmentCheck)
from modules.rag.document_processor import chunk_document
from modules.rag.retriever import PolicyRetriever

SEGMENTATION_POLICY = "Customer Segmentation Policy"

FIELD_LABELS = {
    "days_overdue": "Days the bill is overdue",
    "days_since_active": "Days since last activity",
    "usage_prev_3m": "Usage in the previous 3 months",
    "usage_last_3m": "Usage in the last 3 months",
    "tenure_months": "Tenure (months as a customer)",
    "on_time_payment_ratio": "Share of bills paid on time",
}
OPERATOR_WORDS = {">": "more than", ">=": "at least", "<": "less than", "<=": "at most", "==": "equal to",
                  "!=": "not equal to"}


def _fmt(value: Any, field: str = "") -> str:
    if value is None:
        return "missing"
    if field == "on_time_payment_ratio" and isinstance(value, (int, float)):
        return f"{value:.0%}"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _section_number(title: str) -> str:
    """'2.4 Loyal' -> '2.4', '3. Missing data' -> '3'."""
    head = title.split(" ", 1)[0].rstrip(".")
    return head if re.fullmatch(r"\d+(\.\d+)*", head) else ""


class CustomerOverviewService:
    def __init__(self, retriever: PolicyRetriever, evidence_fn: Callable[[str], dict[str, Any]],
                 segmentation_rules: Callable[[], dict[str, Any]]):
        self.retriever = retriever
        self.evidence_fn = evidence_fn
        self.segmentation_rules = segmentation_rules
        self._sections: dict[tuple[str, str], PolicyQuote] | None = None

    # ------------------------------------------------------------------ policy text lookup
    def _index(self) -> dict[tuple[str, str], PolicyQuote]:
        """(document title, section number) -> sanitised section text, built from the same
        chunks the RAG index uses, so injected instructions are already stripped."""
        if self._sections is None:
            index: dict[tuple[str, str], PolicyQuote] = {}
            for doc in self.retriever.docs:
                for ch in chunk_document(doc):
                    num = _section_number(ch.section)
                    if not num:
                        continue
                    body = ch.text.split("\n", 1)[1].strip() if "\n" in ch.text else ch.text
                    key = (doc.title, num)
                    if key in index:  # long sections are split into several chunks
                        index[key].text += "\n" + body
                    else:
                        index[key] = PolicyQuote(ref=f"{doc.title} §{num}", doc_id=doc.doc_id, doc_name=doc.title,
                                                 section=ch.section, version=doc.version, text=body)
            self._sections = index
        return self._sections

    def quote(self, ref: str | None) -> PolicyQuote | None:
        """Resolve a reference such as 'Payment Reminder Policy §2 (stage 1)' to its section text."""
        if not ref or "§" not in ref:
            return None
        title, rest = (p.strip() for p in ref.split("§", 1))
        num = rest.split()[0].rstrip(".,;") if rest else ""
        q = self._index().get((title, num))
        return q.model_copy(update={"ref": ref}) if q else None

    # ------------------------------------------------------------------ overview
    def overview(self, customer_id: str) -> CustomerOverview:
        ev = self.evidence_fn(customer_id)  # raises NotFoundError for an unknown customer
        seg, strat, prof = ev["segment"], ev["strategy"], ev["profile"]
        rules = self.segmentation_rules()
        priority: list[str] = list(rules.get("priority", []))
        seg_cfg: dict[str, Any] = rules.get("segments", {})

        by_segment: dict[str, list[dict[str, Any]]] = {}
        for e in seg.get("evidence", []):
            by_segment.setdefault(e["segment"], []).append(e)

        checks: list[SegmentCheck] = []
        for name in priority + [s for s in by_segment if s not in priority]:
            cfg = seg_cfg.get(name, {})
            conds = [self._condition(e) for e in by_segment.get(name, [])]
            ref = cfg.get("policy_ref") or next((e.get("policy_ref") for e in by_segment.get(name, [])), None)
            checks.append(SegmentCheck(
                segment=name, description=cfg.get("description", ""), evaluated=bool(conds),
                matched=name in seg.get("segments", []), is_primary=name == seg.get("primary_segment"),
                conditions=conds, policy=self.quote(ref)))

        review = [OverviewReason(reason=r, policy=self.quote(self._manual_review_ref(r)))
                  for r in seg.get("manual_review_reasons", [])]
        blocks = [OverviewReason(reason=f"{b['code']}: {b['detail']}", policy=self.quote(b.get("policy_ref")))
                  for b in strat.get("block_reasons", [])]
        strategy_refs: dict[tuple[str, str], PolicyQuote] = {}
        for q in (self.quote(r) for r in strat.get("policy_refs", [])):
            if q:  # one entry per section; the most specific reference wins ('§2 (stage 2)' over '§2')
                key = (q.doc_id, q.section)
                if key not in strategy_refs or len(q.ref) > len(strategy_refs[key].ref):
                    strategy_refs[key] = q

        offer = strat.get("offer") or None
        return CustomerOverview(
            customer_id=customer_id, status=seg["status"], primary_segment=seg.get("primary_segment"),
            secondary_segments=seg.get("secondary_segments", []), confidence=seg.get("confidence", 0.0),
            headline=self._headline(customer_id, seg, priority), priority=priority, segment_checks=checks,
            manual_review_reasons=review,
            priority_policy=self.quote(f"{SEGMENTATION_POLICY} §1"),
            objective=strat.get("objective"), tone=strat.get("tone"), reminder_stage=strat.get("reminder_stage"),
            offer=f"{offer['name']} ({offer['value']})" if offer else None,
            blocked=bool(strat.get("blocked")), block_reasons=blocks, strategy_policies=list(strategy_refs.values()),
            key_facts=self._facts(prof), data_issues=[f"{i.get('code')}: {i.get('detail')}" for i in prof.get("data_issues", [])],
            data_source=prof.get("data_source"), policy_version=seg.get("policy_version", ""))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _condition(e: dict[str, Any]) -> ConditionCheck:
        field = e["field"]
        label = FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
        op = OPERATOR_WORDS.get(e["operator"], e["operator"])
        threshold = e["threshold"]
        thr = _fmt(threshold, field) if not isinstance(threshold, str) else threshold
        actual = _fmt(e.get("actual"), field)
        verdict = "meets" if e["passed"] else "does not meet"
        near = " (close to the threshold, which lowers confidence)" if e.get("near_threshold") else ""
        return ConditionCheck(
            reason_code=e["reason_code"], field=field, label=label, operator=e["operator"], threshold=thr,
            actual=actual, passed=e["passed"], near_threshold=bool(e.get("near_threshold")),
            explanation=f"{label} is {actual}; the rule needs {op} {thr}, so the customer {verdict} it{near}.")

    @staticmethod
    def _manual_review_ref(reason: str) -> str:
        if reason.startswith("LOW_CONFIDENCE"):
            return f"{SEGMENTATION_POLICY} §4"
        if reason.startswith(("DATA_ISSUE", "MISSING_EVIDENCE")):
            return f"{SEGMENTATION_POLICY} §3"
        return f"{SEGMENTATION_POLICY} §1"

    @staticmethod
    def _headline(cid: str, seg: dict[str, Any], priority: list[str]) -> str:
        if seg["status"] != "CLASSIFIED":
            return (f"{cid} is not assigned to any category and is routed to manual review "
                    f"({len(seg.get('manual_review_reasons', []))} reason(s) below).")
        others = seg.get("secondary_segments", [])
        tail = ""
        if others:
            tail = (f" The customer also matches {', '.join(others)}, but {seg['primary_segment']} comes first "
                    f"in the policy priority ({' > '.join(priority)}).")
        return (f"{cid} belongs to {seg['primary_segment']} (confidence {seg.get('confidence', 0):.2f}): "
                f"every rule for this category is met.{tail}")

    @staticmethod
    def _facts(p: dict[str, Any]) -> dict[str, str]:
        keys = [("tenure_months", "Tenure (months)"), ("contract_type", "Contract"),
                ("monthly_charges", "Monthly charges"), ("payment_status", "Payment status"),
                ("amount_due", "Amount due"), ("days_overdue", "Days overdue"),
                ("on_time_payment_ratio", "Bills paid on time"), ("last_active_date", "Last active"),
                ("days_since_active", "Days since active"), ("usage_last_3m", "Usage last 3 months"),
                ("usage_prev_3m", "Usage previous 3 months"), ("marketing_consent", "Marketing consent"),
                ("last_contacted_date", "Last contacted")]
        return {label: _fmt(p.get(k), k) for k, label in keys}
