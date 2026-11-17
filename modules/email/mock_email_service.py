"""Mock email delivery with a strict pre-send gate (Person 4). No real email is ever sent."""
from __future__ import annotations

import sqlite3
import uuid

from backend.database.db import Database, now_iso
from backend.schemas.models import Draft, DraftStatus
from modules.audit.audit_service import AuditService
from modules.review.draft_repository import DraftRepository
from modules.validation.context import content_hash


class DeliveryError(ValueError):
    pass


def mask_email(addr: str | None) -> str:
    if not addr or "@" not in addr:
        return "(no address)"
    user, domain = addr.split("@", 1)
    return f"{user[:1]}***@{domain}"


class MockEmailService:
    def __init__(self, db: Database, drafts: DraftRepository, audit: AuditService, engagement, customers):
        self.db = db
        self.drafts = drafts
        self.audit = audit
        self.engagement = engagement
        self.customers = customers

    def pre_send_checks(self, draft_id: str) -> tuple[bool, list[str], Draft]:
        d = self.drafts.get(draft_id)
        if d is None:
            raise KeyError(f"Draft {draft_id} not found")
        problems = []
        if self.db.query_one("SELECT 1 FROM mock_deliveries WHERE draft_id = ?", (draft_id,)):
            problems.append("ALREADY_DELIVERED: this draft has already been delivered.")
        if d.status != DraftStatus.APPROVED:
            problems.append(f"NOT_APPROVED: draft status is {d.status.value}; human approval is required.")
        latest = self.drafts.latest_validation(draft_id)
        if latest is None or not latest.passed:
            problems.append("VALIDATION_NOT_PASSED: latest validation did not pass.")
        return not problems, problems, d

    def send(self, draft_id: str, actor: str = "reviewer") -> dict:
        ok, problems, d = self.pre_send_checks(draft_id)
        if not ok:
            self.audit.log("SEND_DENIED", draft_id=draft_id, customer_id=d.customer_id, actor=actor, payload={"problems": problems})
            raise DeliveryError("; ".join(problems))

        # Final gate: re-validate with fresh data (consent, frequency, payment status may have changed)
        report, profile = self.engagement.revalidate(d, "pre_send")
        if not report.passed:
            paid_now = d.objective == "REMIND" and profile.days_overdue == 0 and profile.payment_status == "PAID"
            status = DraftStatus.CANCELLED if paid_now else DraftStatus.BLOCKED
            self.drafts.update_status(draft_id, status)
            reasons = [f"{f.check}: {f.detail}" for f in report.blocking_failures]
            self.audit.log("SEND_CANCELLED" if paid_now else "SEND_BLOCKED", draft_id=draft_id, customer_id=d.customer_id,
                           actor=actor, payload={"reasons": reasons})
            raise DeliveryError(("Customer has already paid; reminder cancelled. " if paid_now else "Pre-send validation failed: ")
                                + "; ".join(reasons))

        message_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
        ts = now_iso()
        try:
            with self.db.transaction() as conn:
                conn.execute("INSERT INTO mock_deliveries (draft_id, message_id, customer_id, to_address_masked, status, created_at) "
                             "VALUES (?,?,?,?,?,?)", (draft_id, message_id, d.customer_id, mask_email(profile.email_address),
                                                      "MOCK_SENT", ts))
                conn.execute("INSERT INTO contact_history (customer_id, draft_id, channel, template_id, objective, is_marketing, "
                             "content_hash, sent_at) VALUES (?,?,?,?,?,?,?,?)",
                             (d.customer_id, draft_id, "EMAIL", d.template_id, d.objective,
                              int(bool(d.strategy.get("is_marketing"))), content_hash(d.subject, d.body), ts))
                conn.execute("UPDATE drafts SET status = ?, updated_at = ? WHERE draft_id = ?",
                             (DraftStatus.MOCK_SENT.value, ts, draft_id))
                conn.execute("UPDATE customers SET last_contacted_date = ? WHERE customer_id = ?", (ts[:10], d.customer_id))
        except sqlite3.IntegrityError as exc:  # concurrent double-click protection
            raise DeliveryError("ALREADY_DELIVERED: duplicate delivery prevented.") from exc
        self.audit.log("MOCK_SENT", draft_id=draft_id, customer_id=d.customer_id, actor=actor,
                       payload={"message_id": message_id, "to": mask_email(profile.email_address)})
        return {"draft_id": draft_id, "message_id": message_id, "status": "MOCK_SENT", "to": mask_email(profile.email_address)}

    def outbox(self, limit: int = 100) -> list[dict]:
        return self.db.query("SELECT * FROM mock_deliveries ORDER BY id DESC LIMIT ?", (limit,))
