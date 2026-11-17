"""Approved offer catalog loaded from policies/offers.yaml (Person 3).

The catalog is configuration, not code: marketing adds a row to the YAML and the policy
rules apply automatically. Nothing outside this catalog can ever be offered.
"""
from __future__ import annotations

from backend.schemas.models import Offer
from config import Settings


def load_catalog(settings: Settings) -> tuple[list[Offer], dict]:
    cfg = settings.offers_config
    offers = [Offer(**o) for o in cfg.get("offers", [])]
    ids = [o.offer_id for o in offers]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate offer IDs in offers.yaml: {sorted(dupes)}")
    return offers, {"version": cfg.get("version", "unknown"), **cfg.get("global_rules", {})}
