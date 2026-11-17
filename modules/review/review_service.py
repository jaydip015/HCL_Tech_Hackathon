"""Human review workflow: approve / edit / reject / regenerate (Person 4).

Rules enforced here (not in the UI):
  * only PENDING_REVIEW drafts whose latest validation passed can be approved;
  * every edit is re-validated; a failed edit moves the draft to NEEDS_FIX (approval disabled);
  * rejected, sent, cancelled drafts are final;
  * regeneration requires reviewer feedback and supersedes the old draft.
"""
from __future__ import annotations

import difflib

from backend.schemas.models import Draft, DraftStatus
from modules.audit.audit_service import AuditService
from modules.review.draft_repository import DraftRepository

FINAL = {DraftStatus.REJECTED, DraftStatus.MOCK_SENT, DraftStatus.CANCELLED}


class ReviewError(ValueError):
    pass


class ReviewService:
    def __init__(self, drafts: DraftRepository, audit: AuditService, engagement):
        self.drafts = drafts
        self.audit = audit
        self.engagement = engagement

    def _get(self, draft_id: str) -> Draft:
        d = self.drafts.get(draft_id)
        if d is None:
            raise KeyError(f"Draft {draft_id} not found")
        return d

    def queue(self, statuses: list[str] | None = None, limit: int = 200) -> list[Draft]:
        statuses = statuses or [DraftStatus.PENDING_REVIEW.value, DraftStatus.NEEDS_FIX.value, DraftStatus.BLOCKED.value,
                                DraftStatus.APPROVED.value]
        return self.drafts.list(statuses, limit=limit)

    def can_approve(self, draft_id: str) -> tuple[bool, str]:
        d = self._get(draft_id)
        if d.status != DraftStatus.PENDING_REVIEW:
            return False, f"Draft is {d.status.value}; only PENDING_REVIEW drafts can be approved."
        report = self.drafts.latest_validation(draft_id)
        if report is None or not report.passed:
            return False, "Latest validation did not pass; fix the draft first."
        return True, "OK"

    def approve(self, draft_id: str, reviewer: str) -> Draft:
        ok, why = self.can_approve(draft_id)
        if not ok:
            self.audit.log("APPROVAL_DENIED", draft_id=draft_id, actor=reviewer, payload={"reason": why})
            raise ReviewError(why)
        self.drafts.update_status(draft_id, DraftStatus.APPROVED)
        self.drafts.add_review(draft_id, reviewer, "APPROVE")
        self.audit.log("APPROVED", draft_id=draft_id, customer_id=self._get(draft_id).customer_id, actor=reviewer)
        return self._get(draft_id)

    def edit(self, draft_id: str, reviewer: str, subject: str, body: str, cta: str | None = None) -> tuple[Draft, object]:
        d = self._get(draft_id)
        if d.status in FINAL:
            raise ReviewError(f"Draft is {d.status.value} and can no longer be edited.")
        if not d.strategy or d.generation_mode == "not_generated":
            raise ReviewError("This draft was blocked before generation (data/policy issue); it cannot be edited into a sendable email.")
        cta = d.cta if cta is None else cta
        diff = {"subject_changed": subject != d.subject,
                "body_diff": list(difflib.unified_diff(d.body.splitlines(), body.splitlines(), lineterm="", n=0))[:60]}
        self.drafts.update_content(draft_id, subject, body, cta, d.status)
        edited = self._get(draft_id)
        report, _ = self.engagement.revalidate(edited, "edit")
        new_status = DraftStatus.PENDING_REVIEW if report.passed else DraftStatus.NEEDS_FIX
        self.drafts.update_status(draft_id, new_status)
        self.drafts.add_review(draft_id, reviewer, "EDIT", diff=diff)
        self.audit.log("EDITED", draft_id=draft_id, customer_id=d.customer_id, actor=reviewer,
                       payload={"revalidation_passed": report.passed, "failure_categories": report.failure_categories,
                                "previous_status": d.status.value, "new_status": new_status.value})
        return self._get(draft_id), report

    def reject(self, draft_id: str, reviewer: str, reason: str) -> Draft:
        if not reason or not reason.strip():
            raise ReviewError("A rejection reason is required.")
        d = self._get(draft_id)
        if d.status in FINAL:
            raise ReviewError(f"Draft is already {d.status.value}.")
        self.drafts.update_status(draft_id, DraftStatus.REJECTED)
        self.drafts.add_review(draft_id, reviewer, "REJECT", reason=reason)
        self.audit.log("REJECTED", draft_id=draft_id, customer_id=d.customer_id, actor=reviewer, payload={"reason": reason})
        return self._get(draft_id)

    def regenerate(self, draft_id: str, reviewer: str, feedback: str) -> Draft:
        if not feedback or not feedback.strip():
            raise ReviewError("Feedback is required to regenerate a draft.")
        d = self._get(draft_id)
        if d.status in (DraftStatus.MOCK_SENT,):
            raise ReviewError("A sent draft cannot be regenerated.")
        self.drafts.add_review(draft_id, reviewer, "REGENERATE", feedback=feedback)
        new = self.engagement.create_draft(d.customer_id, feedback=feedback, actor=reviewer, supersede=True,
                                           forced_offer_id=None)
        if d.status not in FINAL:
            self.drafts.update_status(draft_id, DraftStatus.CANCELLED)
        self.audit.log("REGENERATED", draft_id=draft_id, customer_id=d.customer_id, actor=reviewer,
                       payload={"feedback": feedback, "new_draft_id": new.draft_id})
        return new
