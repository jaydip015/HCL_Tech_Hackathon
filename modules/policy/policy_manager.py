"""Policy document registry and versioning (Person 2).

Records each document's version and SHA-256 in the `policies` table so every decision can
be traced to the exact policy text that was indexed.
"""
from __future__ import annotations

from typing import Any

from backend.database.db import Database, now_iso
from config import Settings
from modules.rag.document_processor import chunk_document
from modules.rag.policy_loader import load_policy_documents


class PolicyManager:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db

    def register_documents(self) -> list[dict[str, Any]]:
        docs = load_policy_documents(self.settings.knowledge_base_dir / "policies")
        rows = []
        for d in docs:
            rows.append((d.doc_id, d.title, d.version, d.sha256, d.path, len(chunk_document(d)), now_iso()))
        self.db.executemany(
            "INSERT OR REPLACE INTO policies (doc_id, doc_name, version, sha256, path, chunk_count, ingested_at) "
            "VALUES (?,?,?,?,?,?,?)", rows)
        return self.list_documents()

    def list_documents(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT doc_id, doc_name, version, sha256, chunk_count, ingested_at FROM policies ORDER BY doc_id")

    def rule_files(self) -> dict[str, str]:
        """Versions of the machine-readable rule files (the enforceable form of the documents)."""
        s = self.settings
        return {
            "segmentation.yaml": s.segmentation.get("version"),
            "communication.yaml": s.communication.get("version"),
            "payment_reminders.yaml": s.reminders.get("version"),
            "offers.yaml": s.offers_config.get("version"),
            "privacy.yaml": s.privacy.get("version"),
        }
