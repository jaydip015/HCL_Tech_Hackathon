"""Append-only audit trail with PII redaction (Person 4)."""
from __future__ import annotations

from typing import Any

from backend.database.db import Database, from_json, now_iso, to_json

REDACT_KEYS_DEFAULT = {"customer_name", "first_name", "email_address", "email", "to_address"}


def redact(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k in keys and v not in (None, "") else redact(v, keys)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, keys) for v in obj]
    return obj


class AuditService:
    def __init__(self, db: Database, redact_keys: list[str] | None = None):
        self.db = db
        self.redact_keys = set(redact_keys or []) | REDACT_KEYS_DEFAULT

    def log(self, event: str, *, draft_id: str | None = None, customer_id: str | None = None,
            actor: str = "system", payload: dict[str, Any] | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_logs (draft_id, customer_id, event, actor, payload_json, created_at) VALUES (?,?,?,?,?,?)",
            (draft_id, customer_id, event, actor, to_json(redact(payload or {}, self.redact_keys)), now_iso()))

    def events(self, draft_id: str | None = None, customer_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if draft_id:
            rows = self.db.query("SELECT * FROM audit_logs WHERE draft_id = ? ORDER BY id", (draft_id,))
        elif customer_id:
            rows = self.db.query("SELECT * FROM audit_logs WHERE customer_id = ? ORDER BY id DESC LIMIT ?", (customer_id, limit))
        else:
            rows = self.db.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["payload"] = from_json(r.pop("payload_json"), {})
        return rows

    def trace(self, draft_id: str) -> dict[str, Any]:
        """Full draft-level trace + the flattened audit record required by the spec."""
        draft = self.db.query_one("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
        if not draft:
            raise KeyError(draft_id)
        attempts = self.db.query("SELECT * FROM generation_attempts WHERE draft_id = ? ORDER BY attempt_no, id", (draft_id,))
        validations = self.db.query("SELECT * FROM validation_reports WHERE draft_id = ? ORDER BY report_id", (draft_id,))
        for v in validations:
            v["findings"] = from_json(v.pop("findings_json"), [])
            v["failure_categories"] = from_json(v.pop("failure_categories_json"), [])
            v["tone_scores"] = from_json(v.pop("tone_scores_json"), None)
        reviews = self.db.query("SELECT * FROM review_actions WHERE draft_id = ? ORDER BY id", (draft_id,))
        delivery = self.db.query_one("SELECT * FROM mock_deliveries WHERE draft_id = ?", (draft_id,))
        segment = from_json(draft.get("segment_json"), {})
        strategy = from_json(draft.get("strategy_json"), {})
        last_review = reviews[-1] if reviews else {}
        rejection = next((r["reason"] for r in reversed(reviews) if r["action"] == "REJECT"), None)
        record = {
            "draft_id": draft_id,
            "customer_id": draft["customer_id"],
            "segments": segment.get("segments", []),
            "reason_codes": segment.get("reason_codes", []),
            "policy_version": draft.get("policy_version"),
            "prompt_version": draft.get("prompt_version"),
            "model_name": draft.get("model_name"),
            "facts_used": redact(from_json(draft.get("facts_used_json"), {}), self.redact_keys),
            "selected_offer": draft.get("offer_id"),
            "validation_result": "PASS" if validations and validations[-1]["passed"] else ("FAIL" if validations else "NOT_RUN"),
            "reviewer_action": last_review.get("action"),
            "rejection_reason": rejection,
            "generation_attempt_count": draft.get("attempt_count", 0),
            "token_usage": {"input": sum(a["input_tokens"] or 0 for a in attempts),
                            "output": sum(a["output_tokens"] or 0 for a in attempts)},
            "latency_ms": sum(a["latency_ms"] or 0 for a in attempts),
            "send_status": draft["status"] if draft["status"] in ("MOCK_SENT", "CANCELLED") else "NOT_SENT",
            "timestamp": draft.get("updated_at"),
            "block_reasons": from_json(draft.get("block_reasons_json"), []),
            "strategy_objective": strategy.get("objective"),
        }
        return {"record": record, "draft": {k: v for k, v in draft.items() if not k.endswith("_json")},
                "attempts": attempts, "validations": validations, "reviews": reviews, "delivery": delivery,
                "events": self.events(draft_id=draft_id)}
