"""Groundedness checks: amounts, dates, numbers and placeholders must come from verified facts (Person 4)."""
from __future__ import annotations

from backend.schemas.models import FailureCategory, ValidationFinding
from backend.services.formatting import extract_dates, extract_money, extract_numbers
from modules.generation.email_generator import unresolved_placeholders
from modules.validation.context import ValidationContext, finding


def _fact_strings(ctx: ValidationContext) -> list[str]:
    return [str(v) for v in ctx.strategy.facts.values() if v not in (None, "")]


def check_amounts(ctx: ValidationContext) -> ValidationFinding:
    found = extract_money(ctx.text_without_allowed())
    allowed = {round(a, 2) for s in _fact_strings(ctx) for a in extract_money(s)}
    tol = float(ctx.reminders.get("amount_tolerance", 0.01))
    bad = [a for a in found if not any(abs(a - b) <= tol for b in allowed)]
    expected = ", ".join(f"{a:,.2f}" for a in sorted(allowed)) or "none"
    return finding("AMOUNT_VERIFICATION", not bad,
                   f"Unsupported amount(s) {', '.join(f'{b:,.2f}' for b in bad)}; verified amount(s): {expected}.",
                   FailureCategory.WRITING, f"All {len(found)} amount(s) match verified billing data.")


def check_percentages(ctx: ValidationContext) -> ValidationFinding:
    """Percentages may only come from the attached approved offer (catches invented discounts)."""
    import re

    pct = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|per\s?cent|percent)", re.I)
    found = [float(x) for x in pct.findall(ctx.text_without_allowed())]
    allowed = {float(x) for s in _fact_strings(ctx) for x in pct.findall(s)}
    bad = sorted({f for f in found if f not in allowed})
    return finding("PERCENTAGE_VERIFICATION", not bad,
                   f"Percentage(s) {[int(b) if b.is_integer() else b for b in bad]} not in the approved offer "
                   f"(approved: {sorted(allowed) or 'none'}).", FailureCategory.WRITING,
                   f"All {len(found)} percentage(s) match the approved offer.")


def check_dates(ctx: ValidationContext) -> ValidationFinding:
    found = extract_dates(ctx.text_without_allowed())
    allowed = {d for s in _fact_strings(ctx) for _, d in extract_dates(s) if d}
    bad = [txt for txt, d in found if d is None or d not in allowed]
    return finding("DATE_VERIFICATION", not bad,
                   f"Unsupported or invalid date(s): {bad}; verified dates: {sorted(str(d) for d in allowed) or 'none'}.",
                   FailureCategory.WRITING, f"All {len(found)} date(s) match verified facts.")


def check_unsupported_numbers(ctx: ValidationContext) -> ValidationFinding:
    """Every number in the email must appear in a verified fact (catches invented tenure,
    percentages, durations, counts ...)."""
    allowed = {round(n, 2) for s in _fact_strings(ctx) for n in extract_numbers(s)}
    found = extract_numbers(ctx.text_without_allowed())
    bad = sorted({n for n in found if round(n, 2) not in allowed})
    pretty = [int(n) if n.is_integer() else n for n in bad]
    return finding("UNSUPPORTED_CLAIMS", not bad,
                   f"Number(s) not supported by verified facts: {pretty}.", FailureCategory.WRITING,
                   "No unsupported numeric claims.")


def check_placeholders(ctx: ValidationContext) -> ValidationFinding:
    left = unresolved_placeholders(ctx.full_text)
    return finding("PLACEHOLDERS_RESOLVED", not left,
                   f"Unknown or unresolved placeholder(s): {sorted(set(left))} (not in verified facts).",
                   FailureCategory.WRITING, "All placeholders resolved from verified facts.")


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    return [check_amounts(ctx), check_percentages(ctx), check_dates(ctx), check_unsupported_numbers(ctx), check_placeholders(ctx)]
