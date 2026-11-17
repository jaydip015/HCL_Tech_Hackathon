"""Payment data consistency, reminder stage and required reminder content (Person 4)."""
from __future__ import annotations

from backend.schemas.models import FailureCategory, ValidationFinding
from modules.strategy.strategy_selector import reminder_stage_for
from modules.validation.context import ValidationContext, finding

PAYMENT_ISSUES = {"CONTRADICTORY_PAYMENT", "MISSING_AMOUNT", "MISSING_DUE_DATE", "INVALID_PAYMENT_STATUS",
                  "NEGATIVE_AMOUNT"}


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    out: list[ValidationFinding] = []
    p, st = ctx.profile, ctx.strategy
    issues = [i for i in p.data_issues if i.code in PAYMENT_ISSUES]
    out.append(finding("PAYMENT_CONSISTENCY", not issues,
                       "; ".join(f"{i.code}: {i.detail}" for i in issues), FailureCategory.DATA,
                       f"Payment status {p.payment_status} is consistent with amount due."))
    blocking_data = [i for i in p.data_issues if i.severity == "BLOCK" and i.code not in PAYMENT_ISSUES]
    out.append(finding("DATA_QUALITY", not blocking_data,
                       "; ".join(f"{i.code}: {i.detail}" for i in blocking_data), FailureCategory.DATA,
                       "Customer data passed quality checks."))
    if st.objective != "REMIND":
        return out
    expected = reminder_stage_for(p.days_overdue, ctx.reminders["stages"])
    ok = expected is not None and expected["stage"] == st.reminder_stage and p.days_overdue > 0
    out.append(finding("OVERDUE_STAGE", ok,
                       f"Reminder stage {st.reminder_stage} does not match {p.days_overdue} days overdue "
                       f"(expected {expected['stage'] if expected else 'none'}).", FailureCategory.POLICY,
                       f"Stage {st.reminder_stage} matches {p.days_overdue} days overdue."))
    return out
