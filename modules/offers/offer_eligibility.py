"""Deterministic offer eligibility (Person 3). Python rules decide; the LLM never does."""
from __future__ import annotations

from datetime import date

from backend.schemas.models import CustomerProfile, Offer, OfferDecision, SegmentResult


def check_offer(offer: Offer, profile: CustomerProfile, segment: SegmentResult, as_of: date,
                rules: dict, channel: str = "EMAIL") -> OfferDecision:
    reasons: list[str] = []
    if offer.status != "ACTIVE":
        reasons.append(f"INACTIVE: offer status is {offer.status}")
    if as_of > offer.expiry_date:
        reasons.append(f"EXPIRED: expired on {offer.expiry_date.isoformat()}")
    if as_of < offer.start_date:
        reasons.append(f"NOT_STARTED: starts on {offer.start_date.isoformat()}")
    primary = segment.primary_segment
    if primary not in offer.eligible_segments:
        reasons.append(f"SEGMENT_NOT_ELIGIBLE: primary segment {primary} not in {offer.eligible_segments}")
    if (profile.tenure_months or 0) < offer.min_tenure_months:
        reasons.append(f"TENURE_TOO_LOW: {profile.tenure_months} < {offer.min_tenure_months} months")
    if channel not in offer.channels:
        reasons.append(f"CHANNEL_NOT_ALLOWED: {channel} not in {offer.channels}")
    if rules.get("require_marketing_consent", True) and profile.marketing_consent is not True:
        reasons.append("NO_CONSENT: marketing consent not verified")
    never = set(rules.get("never_for_segments", []))
    if profile.days_overdue > 0 or never & set(segment.segments):
        reasons.append("OVERDUE: customers with an overdue bill never receive offers")
    return OfferDecision(offer_id=offer.offer_id, eligible=not reasons,
                         reasons=reasons or ["ELIGIBLE: all eligibility rules passed"])


def evaluate_catalog(offers: list[Offer], profile: CustomerProfile, segment: SegmentResult, as_of: date,
                     rules: dict, channel: str = "EMAIL") -> list[OfferDecision]:
    return [check_offer(o, profile, segment, as_of, rules, channel) for o in offers]


def select_offer(offers: list[Offer], decisions: list[OfferDecision]) -> Offer | None:
    """First eligible offer in catalog order (catalog order = business preference)."""
    eligible = {d.offer_id for d in decisions if d.eligible}
    for o in offers:
        if o.offer_id in eligible:
            return o
    return None
