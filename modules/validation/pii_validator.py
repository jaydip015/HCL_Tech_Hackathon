"""PII leakage detection: regex (always) + Microsoft Presidio (when installed) (Person 4)."""
from __future__ import annotations

import re

from backend.schemas.models import FailureCategory, ValidationFinding
from modules.validation.context import ValidationContext, finding

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_URL = re.compile(r"https?://[^\s)>\]]+|www\.[^\s)>\]]+", re.I)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _presidio_hits(text: str) -> list[str]:
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore
    except Exception:
        return []
    try:
        analyzer = AnalyzerEngine()
        res = analyzer.analyze(text=text, language="en",
                               entities=["CREDIT_CARD", "IBAN_CODE", "US_SSN", "IN_AADHAAR", "IN_PAN", "US_BANK_NUMBER"])
        return [f"{r.entity_type}" for r in res if r.score >= 0.6]
    except Exception:
        return []


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    text = ctx.text_without_allowed()
    hits: list[str] = []
    for name, pattern in (ctx.privacy.get("pii_patterns") or {}).items():
        for m in re.finditer(pattern, text):
            digits = re.sub(r"\D", "", m.group(0))
            if name == "card_number" and not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                continue
            hits.append(f"{name}: {m.group(0).strip()[:6]}…")
    hits += [f"unapproved email: {e}" for e in _EMAIL.findall(text)]
    hits += [f"unapproved phone number: {p.strip()}" for p in _PHONE.findall(text) if len(re.sub(r'\D', '', p)) >= 9]
    hits += [f"unapproved link: {u}" for u in _URL.findall(text)]
    if ctx.profile.customer_id in ctx.full_text:
        hits.append("internal customer ID disclosed")
    hits += [f"presidio: {h}" for h in _presidio_hits(text)]
    return [finding("PII_LEAKAGE", not hits, "; ".join(hits), FailureCategory.WRITING,
                    "No card numbers, national IDs, unapproved contacts or links found.")]
