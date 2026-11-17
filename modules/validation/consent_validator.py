"""Consent, contact frequency and duplicate outreach checks (Person 4)."""
from __future__ import annotations

from backend.schemas.models import FailureCategory, ValidationFinding
from modules.validation.context import ValidationContext, content_hash, finding


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    out: list[ValidationFinding] = []
    st, p = ctx.strategy, ctx.profile
    out.append(finding("CONSENT", not st.is_marketing or p.marketing_consent is True,
                       "Marketing email for a customer without verified marketing consent.", FailureCategory.POLICY,
                       "Consent verified." if st.is_marketing else "Service message: marketing consent not required."))

    history = [h for h in ctx.history if h.draft_id != ctx.exclude_draft_id]
    freq = ctx.comm["frequency"]
    cooldown = freq["marketing_cooldown_days"] if st.is_marketing else freq["reminder_cooldown_days"]
    days = []
    if p.last_contacted_date:
        days.append((ctx.as_of - p.last_contacted_date).days)
    days += [(ctx.as_of - h.sent_at.date()).days for h in history]
    last = min(days) if days else None
    out.append(finding("FREQUENCY", last is None or last >= cooldown,
                       f"Customer was contacted {last} day(s) ago; cooldown is {cooldown} days.", FailureCategory.POLICY,
                       f"Last contact {'never' if last is None else f'{last} days ago'}; cooldown {cooldown} days."))

    window = freq["duplicate_window_days"]
    h_now = content_hash(ctx.content.subject, ctx.content.body)
    dup = [h for h in history if (ctx.as_of - h.sent_at.date()).days < window and
           (h.content_hash == h_now or (h.template_id and h.template_id == st.template_id))]
    out.append(finding("DUPLICATE_OUTREACH", not dup,
                       f"Same template or content already sent on {dup[0].sent_at.date() if dup else ''} (window {window} days).",
                       FailureCategory.POLICY, "No duplicate outreach in the last "
                       f"{window} days."))
    return out
