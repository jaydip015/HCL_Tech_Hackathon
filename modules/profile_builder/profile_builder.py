"""Customer profile builder and input-data validation (Person 1).

Turns a stored customer row into a standardised `CustomerProfile` with derived day counts
and a list of data-quality issues. Protected characteristics are never read.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.schemas.models import CustomerProfile, DataIssue, PaymentStatus
from config import Settings

PROFILE_FIELDS = [
    "customer_id", "customer_name", "email_address", "tenure_months", "contract_type", "payment_method",
    "monthly_charges", "total_charges", "usage_last_3m", "usage_prev_3m", "last_active_date", "bill_due_date",
    "amount_due", "payment_status", "on_time_payment_ratio", "marketing_consent", "last_contacted_date",
    "churn_status", "customer_service_calls", "num_complaints", "customer_satisfaction",
    "customer_support_contact", "data_source",
]


def _date(v: Any) -> date | None:
    if v in (None, "") or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _num(v: Any) -> float | None:
    if v in (None, "") or (isinstance(v, float) and v != v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return None if n is None else int(round(n))


def _bool(v: Any) -> bool | None:
    if v in (None, ""):
        return None
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y"}
    return bool(int(v))


def validate_customer_data(p: CustomerProfile, as_of: date) -> list[DataIssue]:
    """Gate 1: data quality. BLOCK issues stop classification and any generation."""
    issues: list[DataIssue] = []
    status = p.payment_status
    if status not in {s.value for s in PaymentStatus}:
        issues.append(DataIssue(code="INVALID_PAYMENT_STATUS", field="payment_status",
                                detail=f"Payment status '{status}' is missing or not recognised."))
    amount = p.amount_due
    if status == "PAID" and amount is not None and amount > 0:
        issues.append(DataIssue(code="CONTRADICTORY_PAYMENT", field="amount_due",
                                detail=f"Marked PAID but has a positive outstanding amount ({amount:.2f})."))
    if status in ("UNPAID", "PARTIAL"):
        if amount is None or amount <= 0:
            issues.append(DataIssue(code="MISSING_AMOUNT", field="amount_due",
                                    detail=f"Status {status} but no positive amount due is recorded."))
        if p.bill_due_date is None:
            issues.append(DataIssue(code="MISSING_DUE_DATE", field="bill_due_date",
                                    detail=f"Status {status} but no bill due date is recorded."))
    if amount is not None and amount < 0:
        issues.append(DataIssue(code="NEGATIVE_AMOUNT", field="amount_due", detail="Amount due is negative."))
    if p.tenure_months is None:
        issues.append(DataIssue(code="MISSING_TENURE", field="tenure_months", detail="Tenure is missing."))
    elif p.tenure_months < 0:
        issues.append(DataIssue(code="INVALID_TENURE", field="tenure_months", detail="Tenure is negative."))
    if p.last_active_date is None:
        issues.append(DataIssue(code="MISSING_ACTIVITY", field="last_active_date", detail="Last activity date is missing."))
    elif p.last_active_date > as_of:
        issues.append(DataIssue(code="FUTURE_ACTIVITY", field="last_active_date", detail="Last activity date is in the future."))
    if p.usage_last_3m is None or p.usage_prev_3m is None:
        issues.append(DataIssue(code="MISSING_USAGE", field="usage_last_3m", detail="Usage history is incomplete."))
    if p.on_time_payment_ratio is not None and not 0 <= p.on_time_payment_ratio <= 1:
        issues.append(DataIssue(code="INVALID_RATIO", field="on_time_payment_ratio", detail="On-time ratio outside 0-1."))
    if p.monthly_charges is not None and p.monthly_charges < 0:
        issues.append(DataIssue(code="INVALID_CHARGES", field="monthly_charges", detail="Monthly charges negative."))
    if p.marketing_consent is None:
        issues.append(DataIssue(code="UNVERIFIED_CONSENT", field="marketing_consent", severity="WARN",
                                detail="Consent not recorded; treated as NO consent."))
    if p.last_contacted_date and p.last_contacted_date > as_of:
        issues.append(DataIssue(code="FUTURE_CONTACT", field="last_contacted_date", severity="WARN",
                                detail="Last contact date is in the future."))
    return issues


def build_profile(row: dict[str, Any], settings: Settings) -> CustomerProfile:
    as_of = settings.as_of_date
    prov = settings.data_mapping.get("provenance", {})
    sources = {f: kind for kind, fields in prov.items() for f in fields}
    if row.get("data_source") == "demo":
        sources = {f: "synthetic (demo)" for f in PROFILE_FIELDS}

    p = CustomerProfile(
        customer_id=str(row["customer_id"]),
        customer_name=row.get("customer_name"),
        email_address=row.get("email_address"),
        tenure_months=_int(row.get("tenure_months")),
        contract_type=row.get("contract_type"),
        payment_method=row.get("payment_method"),
        monthly_charges=_num(row.get("monthly_charges")),
        total_charges=_num(row.get("total_charges")),
        usage_last_3m=_num(row.get("usage_last_3m")),
        usage_prev_3m=_num(row.get("usage_prev_3m")),
        last_active_date=_date(row.get("last_active_date")),
        bill_due_date=_date(row.get("bill_due_date")),
        amount_due=_num(row.get("amount_due")),
        payment_status=(row.get("payment_status") or None),
        on_time_payment_ratio=_num(row.get("on_time_payment_ratio")),
        marketing_consent=_bool(row.get("marketing_consent")),
        last_contacted_date=_date(row.get("last_contacted_date")),
        churn_status=_int(row.get("churn_status")),
        customer_service_calls=_int(row.get("customer_service_calls")),
        num_complaints=_num(row.get("num_complaints")),
        customer_satisfaction=_num(row.get("customer_satisfaction")),
        customer_support_contact=row.get("customer_support_contact"),
        data_source=row.get("data_source"),
        as_of_date=as_of,
        field_sources={f: sources.get(f, "derived") for f in PROFILE_FIELDS if f != "customer_id"},
    )
    if p.last_active_date is not None:
        p.days_since_active = (as_of - p.last_active_date).days
    if p.last_contacted_date is not None:
        p.days_since_contact = (as_of - p.last_contacted_date).days
    if (p.payment_status in ("UNPAID", "PARTIAL") and p.bill_due_date and (p.amount_due or 0) > 0
            and p.bill_due_date < as_of):
        p.days_overdue = (as_of - p.bill_due_date).days
    p.data_issues = validate_customer_data(p, as_of)
    return p


def profile_to_public_dict(p: CustomerProfile) -> dict[str, Any]:
    """Standardised JSON returned by the profile API."""
    return p.model_dump(mode="json")
