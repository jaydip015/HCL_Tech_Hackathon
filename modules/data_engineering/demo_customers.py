"""Hand-crafted, labelled demonstration customers (Person 1).

These drive the end-to-end demo (README section 13 cases A-H) and the evaluation's
classification accuracy. Dates are relative to the configured as_of_date. All values are
synthetic and stored with data_source='demo'.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _d(as_of: date, days: int | None) -> str | None:
    return None if days is None else (as_of - timedelta(days=days)).isoformat()


def _base(cid: str, name: str, as_of: date, support: str, **kw: Any) -> dict[str, Any]:
    row = {
        "customer_id": cid,
        "customer_name": name,
        "email_address": f"{name.split()[0].lower()}.{name.split()[-1].lower()}@example.com",
        "tenure_months": 20,
        "contract_type": "One year",
        "payment_method": "bank_transfer",
        "paperless_billing": "Yes",
        "monthly_charges": 64.50,
        "total_charges": 1290.00,
        "num_services": 3,
        "customer_satisfaction": 8.0,
        "num_complaints": 0.0,
        "customer_service_calls": 1,
        "late_payments": 0,
        "avg_monthly_gb": 80.0,
        "days_since_last_interaction": 10,
        "churn_status": 0,
        "usage_last_3m": 240.0,
        "usage_prev_3m": 236.0,
        "last_active_date": _d(as_of, 10),
        "bill_due_date": (as_of + timedelta(days=12)).isoformat(),
        "amount_due": 0.0,
        "payment_status": "PAID",
        "on_time_payment_ratio": 1.0,
        "marketing_consent": 1,
        "last_contacted_date": _d(as_of, 45),
        "customer_support_contact": support,
        "contact_frequency": "MONTHLY",
        "data_source": "demo",
        "synthetic_seed": None,
    }
    row.update(kw)
    if "days_since_last_interaction" in kw and "last_active_date" not in kw:
        dsl = kw["days_since_last_interaction"]
        row["last_active_date"] = _d(as_of, dsl)
    return row


def demo_customers(as_of: date, support: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (rows, labels). labels[customer_id] holds the expected outcome."""
    rows: list[dict[str, Any]] = []
    labels: dict[str, dict[str, Any]] = {}

    def add(row: dict[str, Any], scenario: str, expected_segment: str | None, expected_status: str,
            description: str, **extra: Any) -> None:
        rows.append(row)
        labels[row["customer_id"]] = {
            "scenario": scenario, "expected_segment": expected_segment,
            "expected_status": expected_status, "description": description, **extra,
        }

    add(_base("DEMO-A-LOYAL", "Priya Sharma", as_of, support, tenure_months=48, total_charges=3120.0,
              contract_type="Two year"),
        "A - Loyal customer", "LOYAL", "PENDING_REVIEW",
        "48 months tenure, always pays on time, consented, not contacted recently.",
        expected_offer="LOYALTY_001")
    add(_base("DEMO-B-DECLINING", "Rohan Mehta", as_of, support, tenure_months=14, usage_last_3m=82.0,
              usage_prev_3m=310.0, days_since_last_interaction=20, on_time_payment_ratio=0.9),
        "B - Declining customer", "DECLINING", "PENDING_REVIEW",
        "Usage fell from 310 GB to 82 GB over the last quarter.", expected_offer="REENGAGE_001")
    add(_base("DEMO-C-DORMANT", "Ananya Iyer", as_of, support, tenure_months=26, usage_last_3m=4.0,
              usage_prev_3m=180.0, days_since_last_interaction=100, on_time_payment_ratio=0.92),
        "C - Dormant customer", "DORMANT", "PENDING_REVIEW",
        "No activity for 100 days.", expected_offer="WINBACK_001")
    add(_base("DEMO-D-OVERDUE", "Vikram Rao", as_of, support, tenure_months=40, payment_status="UNPAID",
              amount_due=134.40, monthly_charges=67.20, bill_due_date=_d(as_of, 20), on_time_payment_ratio=0.8,
              late_payments=3),
        "D - Overdue customer (stage 2)", "OVERDUE", "PENDING_REVIEW",
        "Bill of $134.40 overdue by 20 days; also loyal (secondary segment). No promotions allowed.",
        expected_stage=2)
    add(_base("DEMO-D1-OVERDUE-S1", "Kavya Nair", as_of, support, tenure_months=9, payment_status="UNPAID",
              amount_due=58.90, monthly_charges=58.90, bill_due_date=_d(as_of, 7), on_time_payment_ratio=0.88),
        "D1 - Overdue customer (stage 1)", "OVERDUE", "PENDING_REVIEW",
        "Bill overdue by 7 days: courteous reminder.", expected_stage=1)
    add(_base("DEMO-D3-OVERDUE-S3", "Arjun Das", as_of, support, tenure_months=30, payment_status="PARTIAL",
              amount_due=92.15, monthly_charges=71.00, bill_due_date=_d(as_of, 45), on_time_payment_ratio=0.7,
              late_payments=6),
        "D3 - Overdue customer (stage 3)", "OVERDUE", "PENDING_REVIEW",
        "Partial payment, balance overdue by 45 days: formal notice.", expected_stage=3)
    add(_base("DEMO-E-NOCONSENT", "Meera Pillai", as_of, support, tenure_months=55, marketing_consent=0),
        "E - No consent", "LOYAL", "BLOCKED",
        "Loyal customer who has not consented to marketing: promotional email must be blocked.",
        expected_block="NO_CONSENT")
    add(_base("DEMO-F-EXPIRED-OFFER", "Rahul Verma", as_of, support, tenure_months=52),
        "F - Invalid (expired) offer", "LOYAL", "PENDING_REVIEW",
        "Generate with forced offer LOYALTY_2025 (expired): it must be rejected and a valid offer used.",
        forced_offer="LOYALTY_2025", expected_offer="LOYALTY_001")
    add(_base("DEMO-G-HALLUCINATION", "Sneha Kulkarni", as_of, support, tenure_months=18, payment_status="UNPAID",
              amount_due=79.99, monthly_charges=79.99, bill_due_date=_d(as_of, 10), on_time_payment_ratio=0.9),
        "G - Hallucinated amount", "OVERDUE", "PENDING_REVIEW",
        "Generate with fault injection: first draft states a wrong amount; validator must catch it.",
        inject_fault="wrong_amount", expected_stage=1)
    add(_base("DEMO-H-CONTRADICTORY", "Karan Malhotra", as_of, support, payment_status="PAID", amount_due=45.00,
              bill_due_date=_d(as_of, 12)),
        "H - Contradictory payment data", None, "BLOCKED",
        "Marked PAID but has $45.00 outstanding: data failure, manual escalation, no reminder.",
        expected_block="DATA_ISSUE")
    add(_base("DEMO-I-RECENT-CONTACT", "Divya Menon", as_of, support, tenure_months=60, last_contacted_date=_d(as_of, 2)),
        "I - Recently contacted", "LOYAL", "BLOCKED",
        "Contacted 2 days ago: blocked by the 7-day marketing cooldown.", expected_block="RECENT_CONTACT")
    add(_base("DEMO-J-MISSING", "Samuel Okafor", as_of, support, tenure_months=None, usage_last_3m=None,
              last_active_date=None, days_since_last_interaction=None),
        "J - Missing customer evidence", None, "BLOCKED",
        "Tenure, usage and activity are missing: no classification is fabricated.",
        expected_block="DATA_ISSUE")
    add(_base("DEMO-K-CONSISTENT", "Grace Lewis", as_of, support, tenure_months=22, days_since_last_interaction=5),
        "K - Consistent customer", "CONSISTENT", "PENDING_REVIEW",
        "Pays on time and active this week: appreciation email.", expected_offer="THANKS_001")
    return rows, labels
