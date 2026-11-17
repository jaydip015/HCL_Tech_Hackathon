"""Shared input bundle for all validators (Person 4)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.schemas.models import (ContactRecord, CustomerProfile, EmailContent, FailureCategory, SegmentResult,
                                    Strategy, ValidationFinding)


@dataclass
class ValidationContext:
    content: EmailContent
    strategy: Strategy
    profile: CustomerProfile
    segment: SegmentResult
    history: list[ContactRecord]
    comm: dict[str, Any]
    reminders: dict[str, Any]
    privacy: dict[str, Any]
    as_of: date
    offers_repo: Any
    exclude_draft_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return f"{self.content.subject}\n{self.content.body}\n{self.content.cta}"

    @property
    def allowed_literals(self) -> list[str]:
        """Approved strings (support contacts, company name, customer's own email) that may
        contain digits/addresses and are removed before numeric/PII scanning."""
        sup = self.comm["support"]
        vals = [sup["dispute_url"], sup["email"], sup["phone"], sup["company_name"]]
        if self.profile.email_address:
            vals.append(self.profile.email_address)
        return sorted(vals, key=len, reverse=True)

    def text_without_allowed(self) -> str:
        t = self.full_text
        for lit in self.allowed_literals:
            t = t.replace(lit, " ")
        return t


def finding(check: str, ok: bool, detail_fail: str, category: FailureCategory | None, detail_pass: str = "",
            severity: str = "BLOCK") -> ValidationFinding:
    return ValidationFinding(check=check, status="PASS" if ok else "FAIL", severity=severity,
                             category=None if ok else category, detail=detail_pass if ok else detail_fail)


def warn(check: str, detail: str, category: FailureCategory | None = FailureCategory.WRITING) -> ValidationFinding:
    return ValidationFinding(check=check, status="WARN", severity="WARN", category=category, detail=detail)


def contains_term(text: str, term: str) -> bool:
    """Case-insensitive term match with word boundaries for alphabetic terms; ALL-CAPS terms
    (internal codes such as OVERDUE) are matched case-sensitively."""
    if term.isupper():
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    if re.fullmatch(r"[A-Za-z ]+", term.strip()):
        return re.search(rf"\b{re.escape(term.strip())}\b", text, re.I) is not None
    return term.lower() in text.lower()


def content_hash(subject: str, body: str) -> str:
    norm = re.sub(r"\s+", " ", f"{subject}|{body}".strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]
