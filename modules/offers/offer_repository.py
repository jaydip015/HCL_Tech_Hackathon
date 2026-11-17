"""Offer catalog access + persistence of the approved catalog snapshot (Person 3)."""
from __future__ import annotations

from backend.database.db import Database, now_iso, to_json
from backend.schemas.models import Offer
from config import Settings
from modules.offers.offer_catalog import load_catalog


class OfferRepository:
    def __init__(self, settings: Settings, db: Database | None = None):
        self.settings = settings
        self.db = db
        self.reload()

    def reload(self) -> None:
        self._offers, self.rules = load_catalog(self.settings)
        self.version = self.rules.get("version", "unknown")
        self._by_id = {o.offer_id: o for o in self._offers}
        if self.db is not None:
            self.db.executemany(
                "INSERT OR REPLACE INTO offers (offer_id, offer_json, catalog_version, updated_at) VALUES (?,?,?,?)",
                [(o.offer_id, to_json(o), self.version, now_iso()) for o in self._offers])

    def all(self) -> list[Offer]:
        return list(self._offers)

    def get(self, offer_id: str | None) -> Offer | None:
        return self._by_id.get(offer_id) if offer_id else None

    def names_and_ids(self) -> list[tuple[str, str]]:
        return [(o.offer_id, o.name) for o in self._offers]
