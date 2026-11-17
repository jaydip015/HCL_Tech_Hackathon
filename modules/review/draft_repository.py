"""Draft persistence: drafts, attempts, validation reports, review actions (Person 4)."""
from __future__ import annotations

from typing import Any

from backend.database.db import Database, from_json, now_iso, to_json
from backend.schemas.models import ContactRecord, Draft, DraftStatus, GenerationAttempt, ValidationReport
from modules.validation.context import content_hash


class DraftRepository:
    def __init__(self, db: Database):
        self.db = db

    def insert(self, d: Draft) -> None:
        ts = now_iso()
        self.db.execute(
            """INSERT INTO drafts (draft_id, customer_id, status, subject, body, cta, objective, tone, template_id,
                 offer_id, reminder_stage, facts_used_json, strategy_json, segment_json, block_reasons_json,
                 prompt_version, model_name, policy_version, generation_mode, attempt_count, content_hash,
                 created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.draft_id, d.customer_id, d.status.value, d.subject, d.body, d.cta, d.objective, d.tone, d.template_id,
             d.offer_id, d.reminder_stage, to_json(d.facts_used), to_json(d.strategy), to_json(d.segment),
             to_json(d.block_reasons), d.prompt_version, d.model_name, d.policy_version, d.generation_mode,
             d.attempt_count, content_hash(d.subject, d.body) if d.body else None, ts, ts))

    def update_status(self, draft_id: str, status: DraftStatus) -> None:
        self.db.execute("UPDATE drafts SET status = ?, updated_at = ? WHERE draft_id = ?", (status.value, now_iso(), draft_id))

    def update_content(self, draft_id: str, subject: str, body: str, cta: str, status: DraftStatus) -> None:
        self.db.execute("UPDATE drafts SET subject=?, body=?, cta=?, status=?, content_hash=?, updated_at=? WHERE draft_id=?",
                        (subject, body, cta, status.value, content_hash(subject, body), now_iso(), draft_id))

    def get(self, draft_id: str) -> Draft | None:
        row = self.db.query_one("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
        return self._to_model(row) if row else None

    def _to_model(self, row: dict[str, Any]) -> Draft:
        return Draft(
            draft_id=row["draft_id"], customer_id=row["customer_id"], status=DraftStatus(row["status"]),
            subject=row["subject"] or "", body=row["body"] or "", cta=row["cta"] or "", objective=row["objective"],
            tone=row["tone"], template_id=row["template_id"], offer_id=row["offer_id"], reminder_stage=row["reminder_stage"],
            facts_used=from_json(row["facts_used_json"], {}), strategy=from_json(row["strategy_json"], {}),
            segment=from_json(row["segment_json"], {}), block_reasons=from_json(row["block_reasons_json"], []),
            prompt_version=row["prompt_version"], model_name=row["model_name"], policy_version=row["policy_version"],
            generation_mode=row["generation_mode"], attempt_count=row["attempt_count"] or 0,
            created_at=row["created_at"].rstrip("Z") if row["created_at"] else None,
            updated_at=row["updated_at"].rstrip("Z") if row["updated_at"] else None)

    def list(self, statuses: list[str] | None = None, customer_id: str | None = None, limit: int = 200) -> list[Draft]:
        clauses, params = [], []
        if statuses:
            clauses.append(f"status IN ({','.join('?' * len(statuses))})")
            params += statuses
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.db.query(f"SELECT * FROM drafts {where} ORDER BY updated_at DESC, created_at DESC LIMIT ?", (*params, limit))
        return [self._to_model(r) for r in rows]

    def open_draft_for(self, customer_id: str) -> Draft | None:
        drafts = self.list([DraftStatus.PENDING_REVIEW.value, DraftStatus.NEEDS_FIX.value, DraftStatus.APPROVED.value],
                           customer_id=customer_id, limit=1)
        return drafts[0] if drafts else None

    # ---------------------------------------------------------- related records
    def add_attempts(self, draft_id: str, attempts: list[GenerationAttempt]) -> None:
        ts = now_iso()
        self.db.executemany(
            """INSERT INTO generation_attempts (draft_id, attempt_no, mode, model_name, prompt_version, latency_ms,
               input_tokens, output_tokens, passed, failure_categories_json, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(draft_id, a.attempt_no, a.mode, a.model_name, a.prompt_version, a.latency_ms, a.input_tokens,
              a.output_tokens, int(a.passed), to_json(a.failure_categories), a.error, ts) for a in attempts])

    def attempts(self, draft_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM generation_attempts WHERE draft_id = ? ORDER BY attempt_no, id", (draft_id,))

    def add_validation(self, draft_id: str, report: ValidationReport, source: str) -> None:
        self.db.execute(
            """INSERT INTO validation_reports (draft_id, source, passed, retry_recommended, failure_categories_json,
               findings_json, tone_scores_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (draft_id, source, int(report.passed), int(report.retry_recommended), to_json(report.failure_categories),
             to_json([f.model_dump(mode="json") for f in report.findings]), to_json(report.tone_scores), now_iso()))

    def latest_validation(self, draft_id: str) -> ValidationReport | None:
        row = self.db.query_one("SELECT * FROM validation_reports WHERE draft_id = ? ORDER BY report_id DESC LIMIT 1", (draft_id,))
        if not row:
            return None
        return ValidationReport(draft_id=draft_id, passed=bool(row["passed"]), findings=from_json(row["findings_json"], []),
                                retry_recommended=bool(row["retry_recommended"]),
                                failure_categories=from_json(row["failure_categories_json"], []),
                                tone_scores=from_json(row["tone_scores_json"], None))

    def add_review(self, draft_id: str, reviewer: str, action: str, reason: str | None = None,
                   feedback: str | None = None, diff: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO review_actions (draft_id, reviewer, action, reason, feedback, diff_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (draft_id, reviewer, action, reason, feedback, to_json(diff or {}), now_iso()))

    def reviews(self, draft_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM review_actions WHERE draft_id = ? ORDER BY id", (draft_id,))

    def save_strategy(self, customer_id: str, draft_id: str | None, strategy: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO strategies (customer_id, draft_id, strategy_json, created_at) VALUES (?,?,?,?)",
                        (customer_id, draft_id, to_json(strategy), now_iso()))

    # ---------------------------------------------------------- contact history
    def contact_history(self, customer_id: str) -> list[ContactRecord]:
        rows = self.db.query("SELECT * FROM contact_history WHERE customer_id = ? ORDER BY sent_at DESC", (customer_id,))
        return [ContactRecord(customer_id=r["customer_id"], draft_id=r["draft_id"], template_id=r["template_id"],
                              objective=r["objective"], is_marketing=bool(r["is_marketing"]),
                              content_hash=r["content_hash"], sent_at=r["sent_at"].rstrip("Z")) for r in rows]
