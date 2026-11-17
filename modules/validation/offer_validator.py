"""Offer checks: existence, eligibility, expiry, exact terms, no unapproved promotions (Person 4)."""
from __future__ import annotations

from backend.schemas.models import FailureCategory, ValidationFinding
from backend.services.formatting import fmt_date
from modules.offers.offer_eligibility import check_offer
from modules.validation.context import ValidationContext, contains_term, finding


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    out: list[ValidationFinding] = []
    st, text = ctx.strategy, ctx.full_text
    promo_terms = ctx.comm.get("promo_terms", [])
    catalog = ctx.offers_repo.all()

    # Mentions of catalog offers other than the attached one
    attached_id = st.offer.offer_id if st.offer else None
    others = [o.offer_id for o in catalog if o.offer_id != attached_id and
              (o.offer_id in text or (o.name.lower() in text.lower() and (not st.offer or o.name != st.offer.name)))]

    if st.objective == "REMIND":
        promo = [t for t in promo_terms if contains_term(text, t)]
        out.append(finding("NO_PROMO_IN_REMINDER", not promo and not st.offer and not others,
                           f"Payment reminder contains promotional content: {promo or others or [attached_id]}.",
                           FailureCategory.WRITING if not st.offer else FailureCategory.POLICY,
                           "Reminder contains no promotional content."))
        return out

    if st.offer is None:
        promo = [t for t in promo_terms if contains_term(text, t)]
        out.append(finding("UNAPPROVED_PROMOTION", not promo and not others,
                           f"No approved offer is attached but the email contains promotional content: {promo + others}.",
                           FailureCategory.WRITING, "No offer attached and none mentioned."))
        return out

    offer = ctx.offers_repo.get(st.offer.offer_id)
    out.append(finding("OFFER_EXISTENCE", offer is not None,
                       f"Offer {st.offer.offer_id} does not exist in the approved catalog.", FailureCategory.POLICY,
                       f"Offer {st.offer.offer_id} exists in catalog {ctx.offers_repo.version}."))
    if offer is None:
        return out
    dec = check_offer(offer, ctx.profile, ctx.segment, ctx.as_of, ctx.offers_repo.rules)
    expired = any(r.startswith(("EXPIRED", "NOT_STARTED")) for r in dec.reasons)
    out.append(finding("OFFER_EXPIRY", not expired, f"Offer {offer.offer_id} is not currently valid: {dec.reasons}.",
                       FailureCategory.POLICY, f"Valid until {offer.expiry_date.isoformat()}."))
    other_reasons = [r for r in dec.reasons if not r.startswith(("EXPIRED", "NOT_STARTED"))]
    out.append(finding("OFFER_ELIGIBILITY", dec.eligible or (expired and not other_reasons),
                       f"Customer is not eligible for {offer.offer_id}: {other_reasons}.", FailureCategory.POLICY,
                       "Offer is valid for this customer and segment."))
    missing = [label for label, val in (("value", offer.value), ("terms", offer.terms),
                                        ("expiry", fmt_date(offer.expiry_date))) if val not in text]
    changed = st.offer.model_dump() != offer.model_dump()
    out.append(finding("OFFER_TERMS", not missing and not changed and not others,
                       (f"Offer text must state value, terms and expiry exactly as approved; missing: {missing}. "
                        if missing else "") + ("Offer details differ from the catalog. " if changed else "")
                       + (f"Mentions other offers: {others}." if others else ""),
                       FailureCategory.WRITING if not changed else FailureCategory.POLICY,
                       "Offer value, terms and expiry stated exactly as approved."))
    return out
