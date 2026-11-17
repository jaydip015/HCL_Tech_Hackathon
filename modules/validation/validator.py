"""Deterministic validation engine (Person 4).

Runs all checks and returns a ValidationReport. A report passes only when no BLOCK-severity
check fails. Failures are categorised so the generation loop knows what to do:
  DATA / POLICY  -> block or recompute strategy, never call the LLM again
  WRITING        -> targeted repair prompt
  FORMAT         -> one format retry
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.schemas.models import (ContactRecord, CustomerProfile, EmailContent, FailureCategory, SegmentResult,
                                    Strategy, ValidationFinding, ValidationReport)
from config import Settings
from modules.validation import consent_validator, fact_validator, offer_validator, payment_validator, pii_validator, tone_validator
from modules.validation.context import ValidationContext, contains_term, finding

CHECK_ORDER = [
    "SCHEMA", "AMOUNT_VERIFICATION", "PERCENTAGE_VERIFICATION", "DATE_VERIFICATION", "UNSUPPORTED_CLAIMS", "PLACEHOLDERS_RESOLVED",
    "OFFER_EXISTENCE", "OFFER_ELIGIBILITY", "OFFER_EXPIRY", "OFFER_TERMS", "UNAPPROVED_PROMOTION",
    "NO_PROMO_IN_REMINDER", "PAYMENT_CONSISTENCY", "DATA_QUALITY", "OVERDUE_STAGE", "CONSENT", "FREQUENCY",
    "DUPLICATE_OUTREACH", "PROHIBITED_PHRASES", "INTERNAL_DISCLOSURE", "PII_LEAKAGE", "REQUIRED_CONTENT",
    "SUPPORT_CONTACT", "TONE_MATCH", "TONE_EXCLAMATIONS", "TONE_ALL_CAPS", "TONE_JUDGE",
]


class EmailValidator:
    def __init__(self, settings: Settings, offers_repo: Any):
        self.settings = settings
        self.offers_repo = offers_repo

    # -------------------------------------------------------------- helpers
    def _schema(self, content: Any) -> tuple[EmailContent | None, ValidationFinding]:
        length = self.settings.communication.get("length", {})
        try:
            ec = content if isinstance(content, EmailContent) else EmailContent(**(content or {}))
        except (ValidationError, TypeError) as exc:
            return None, finding("SCHEMA", False, f"Output does not match the email schema: {str(exc)[:200]}",
                                 FailureCategory.FORMAT)
        problems = []
        if len(ec.subject) > length.get("subject_max", 120):
            problems.append("subject too long")
        if len(ec.body) < length.get("body_min", 60):
            problems.append("body too short")
        if len(ec.body) > length.get("body_max", 2500):
            problems.append("body too long")
        return ec, finding("SCHEMA", not problems, f"Schema/length problems: {problems}", FailureCategory.FORMAT,
                           "Subject, body and CTA match the schema and length limits.")

    def _required_content(self, ctx: ValidationContext) -> list[ValidationFinding]:
        st, facts, text = ctx.strategy, ctx.strategy.facts, ctx.full_text
        if st.objective == "REMIND":
            keys = list(ctx.reminders.get("must_include", []))
        else:
            keys = ["first_name"]
        missing = [k for k in keys if facts.get(k) not in (None, "") and str(facts[k]) not in text]
        out = [finding("REQUIRED_CONTENT", not missing, f"Required verified fact(s) missing: {missing}.",
                       FailureCategory.WRITING, f"Contains required facts: {keys}.")]
        sup = ctx.comm["support"]
        has_support = sup["phone"] in text or sup["email"] in text
        needs_dispute = st.objective == "REMIND"
        has_dispute = sup["dispute_url"] in text
        ok = has_support and (has_dispute or not needs_dispute)
        out.append(finding("SUPPORT_CONTACT", ok,
                           "Missing support contact" + (" and billing dispute link" if needs_dispute and not has_dispute else "") + ".",
                           FailureCategory.WRITING,
                           "Support contact" + (" and dispute link" if needs_dispute else "") + " included."))
        return out

    # -------------------------------------------------------------- main entry
    def validate(self, content: Any, strategy: Strategy, profile: CustomerProfile, segment: SegmentResult,
                 history: list[ContactRecord] | None = None, draft_id: str | None = None,
                 exclude_draft_id: str | None = None) -> ValidationReport:
        ec, schema_finding = self._schema(content)
        findings: list[ValidationFinding] = [schema_finding]
        if ec is not None:
            s = self.settings
            ctx = ValidationContext(content=ec, strategy=strategy, profile=profile, segment=segment,
                                    history=history or [], comm=s.communication, reminders=s.reminders,
                                    privacy=s.privacy, as_of=s.as_of_date, offers_repo=self.offers_repo,
                                    exclude_draft_id=exclude_draft_id or draft_id)
            findings += fact_validator.run(ctx)
            findings += offer_validator.run(ctx)
            findings += payment_validator.run(ctx)
            findings += consent_validator.run(ctx)
            findings += tone_validator.run(ctx)
            findings += pii_validator.run(ctx)
            findings += self._required_content(ctx)
        else:
            # Data/policy checks still run so a broken format never hides a policy problem
            findings += [f for f in payment_validator.run(self._bare_ctx(strategy, profile, segment, history))
                         if f.status == "FAIL"]
        findings.sort(key=lambda f: CHECK_ORDER.index(f.check) if f.check in CHECK_ORDER else 99)
        return self.summarise(findings, draft_id)

    def _bare_ctx(self, strategy: Strategy, profile: CustomerProfile, segment: SegmentResult,
                  history: list[ContactRecord] | None) -> ValidationContext:
        s = self.settings
        dummy = EmailContent(subject="n/a", body="n/a " * 10, cta="")
        return ValidationContext(content=dummy, strategy=strategy, profile=profile, segment=segment,
                                 history=history or [], comm=s.communication, reminders=s.reminders,
                                 privacy=s.privacy, as_of=s.as_of_date, offers_repo=self.offers_repo)

    @staticmethod
    def summarise(findings: list[ValidationFinding], draft_id: str | None = None,
                  tone_scores: dict | None = None) -> ValidationReport:
        blocking = [f for f in findings if f.status == "FAIL" and f.severity == "BLOCK"]
        cats = sorted({f.category.value for f in blocking if f.category})
        retry = bool(blocking) and set(cats) <= {FailureCategory.WRITING.value, FailureCategory.FORMAT.value}
        return ValidationReport(draft_id=draft_id, passed=not blocking, findings=findings, retry_recommended=retry,
                                failure_categories=cats, tone_scores=tone_scores)


def failure_messages(report: ValidationReport) -> list[str]:
    return [f"{f.check}: {f.detail}" for f in report.blocking_failures]


__all__ = ["EmailValidator", "failure_messages", "contains_term"]
