"""Deterministic synthetic enrichment (Person 1).

The Kaggle churn dataset has no names, billing dates, consent or contact history, so these
are generated here. Every synthetic value is:
  * deterministic: derived from hash(seed, customer_id, field), so it is identical across runs
    and independent of chunk size;
  * clearly labelled: provenance is listed in config/data_mapping.yaml and shown in the UI;
  * internally consistent: PAID => amount_due 0; overdue durations match due dates, etc.
Protected attributes are never inputs to any synthetic value.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

FIRST_NAMES = [
    "Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Meera", "Arjun", "Kavya", "Rahul", "Sneha",
    "James", "Olivia", "Liam", "Emma", "Noah", "Sophia", "Mateo", "Isabella", "Lucas", "Mia",
    "Wei", "Mei", "Hiro", "Yuki", "Omar", "Layla", "Kwame", "Amara", "Diego", "Lucia",
    "Ethan", "Ava", "Ravi", "Divya", "Karan", "Nisha", "Samuel", "Grace", "Ali", "Zara",
]
LAST_NAMES = [
    "Sharma", "Iyer", "Patel", "Reddy", "Khan", "Gupta", "Nair", "Singh", "Das", "Menon",
    "Smith", "Johnson", "Brown", "Garcia", "Miller", "Davis", "Wilson", "Lopez", "Clark", "Lewis",
    "Chen", "Wang", "Tanaka", "Sato", "Hassan", "Mensah", "Okafor", "Silva", "Rossi", "Muller",
]
CONTACT_FREQUENCIES = ["MONTHLY", "QUARTERLY", "WEEKLY"]


def _uniform(ids: pd.Series, seed: int, field: str) -> np.ndarray:
    """Deterministic U[0,1) per customer and field."""
    keys = ids.astype(str) + f"|{seed}|{field}"
    hashed = pd.util.hash_pandas_object(keys, index=False).to_numpy(dtype=np.uint64)
    return (hashed >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def enrich_chunk(df: pd.DataFrame, as_of: date, seed: int, support_contact: str) -> pd.DataFrame:
    out = df.copy()
    ids = out["customer_id"]
    n = len(out)
    if n == 0:
        return out
    u = lambda f: _uniform(ids, seed, f)  # noqa: E731

    # --- identity (synthetic)
    first = np.array(FIRST_NAMES)[(u("first") * len(FIRST_NAMES)).astype(int)]
    last = np.array(LAST_NAMES)[(u("last") * len(LAST_NAMES)).astype(int)]
    out["customer_name"] = pd.Series(first, index=out.index) + " " + pd.Series(last, index=out.index)
    suffix = (u("email") * 1000).astype(int)
    out["email_address"] = [f"{f.lower()}.{l.lower()}{s}@example.com" for f, l, s in zip(first, last, suffix)]

    # --- activity
    days_since = pd.to_numeric(out.get("days_since_last_interaction"), errors="coerce")
    out["last_active_date"] = [
        (as_of - timedelta(days=int(d))).isoformat() if pd.notna(d) else None for d in days_since
    ]  # DERIVED from original days_since_last_interaction

    gb = pd.to_numeric(out.get("avg_monthly_gb"), errors="coerce")
    prev = (gb * 3 * (0.9 + 0.2 * u("prev"))).round(2)  # DERIVED (original avg + small noise)
    churn = pd.to_numeric(out.get("churn_status"), errors="coerce").fillna(0).to_numpy()
    r_decl, r_mag = u("decline"), u("decline_mag")
    factor = 0.85 + 0.30 * u("trend")                         # stable usage by default
    declining = ((churn == 1) & (r_decl < 0.6)) | ((churn != 1) & (r_decl < 0.08))
    factor = np.where(declining, 0.20 + 0.35 * r_mag, factor)
    inactive = days_since.fillna(0).to_numpy() >= 90
    factor = np.where(inactive, 0.20 * r_mag, factor)
    out["usage_prev_3m"] = prev
    out["usage_last_3m"] = (prev * factor).round(2)            # SYNTHETIC trend

    # --- billing (synthetic, internally consistent)
    late = pd.to_numeric(out.get("late_payments"), errors="coerce").fillna(0).to_numpy()
    monthly = pd.to_numeric(out.get("monthly_charges"), errors="coerce").to_numpy()
    p_unpaid = np.clip(0.03 + 0.06 * late, 0, 0.6)
    r_pay, r_part, r_due, r_amt, r_future = u("pay"), u("partial"), u("due"), u("amt"), u("future")
    status, due_dates, amounts = [], [], []
    for i in range(n):
        m = monthly[i]
        if np.isnan(m) or r_pay[i] >= p_unpaid[i]:
            status.append("PAID")
            due_dates.append((as_of + timedelta(days=1 + int(r_due[i] * 27))).isoformat())  # next bill
            amounts.append(0.0)
            continue
        st = "PARTIAL" if r_part[i] < 0.2 else "UNPAID"
        if r_future[i] < 0.3:  # bill issued but not yet due
            due = as_of + timedelta(days=1 + int(r_due[i] * 14))
            months = 1
        else:
            overdue = 1 + int(r_due[i] * min(120, 10 + 15 * late[i]))
            due = as_of - timedelta(days=overdue)
            months = 1 + overdue // 30
        amt = m * months if st == "UNPAID" else m * (0.3 + 0.4 * r_amt[i])
        status.append(st)
        due_dates.append(due.isoformat())
        amounts.append(round(float(amt), 2))
    out["payment_status"] = status
    out["bill_due_date"] = due_dates
    out["amount_due"] = amounts

    tenure = pd.to_numeric(out.get("tenure_months"), errors="coerce")
    bills = tenure.clip(lower=1, upper=36).fillna(1)
    out["on_time_payment_ratio"] = (1 - pd.Series(late, index=out.index) / bills).clip(0, 1).round(3)  # DERIVED

    # --- consent and contact history (synthetic)
    out["marketing_consent"] = (u("consent") < 0.85).astype(int)
    out["last_contacted_date"] = [
        (as_of - timedelta(days=1 + int(d * 120))).isoformat() if c < 0.6 else None
        for c, d in zip(u("contact"), u("contact_days"))
    ]
    out["customer_support_contact"] = support_contact
    out["contact_frequency"] = np.array(CONTACT_FREQUENCIES)[(u("freq") * 3).astype(int)]
    out["synthetic_seed"] = seed
    return out


SYNTHETIC_FIELDS: list[str] = [
    "customer_name", "email_address", "usage_last_3m", "bill_due_date", "amount_due", "payment_status",
    "marketing_consent", "last_contacted_date", "customer_support_contact", "contact_frequency",
]
DERIVED_FIELDS: list[str] = ["last_active_date", "on_time_payment_ratio", "usage_prev_3m"]


def describe_rules() -> dict[str, Any]:
    """Human-readable generation rules (shown in README and the Customer Explorer)."""
    return {
        "customer_name/email_address": "Picked from fixed name lists by hash(seed, customer_id); emails use example.com.",
        "last_active_date": "DERIVED: as_of_date - days_since_last_interaction (original column).",
        "usage_prev_3m": "DERIVED: avg_monthly_gb x 3 with +/-10% noise.",
        "usage_last_3m": "SYNTHETIC: stable (85-115% of prev); churned customers decline with 60% prob; 90+ days inactive => <20%.",
        "payment_status/amount_due/bill_due_date": "SYNTHETIC: unpaid probability rises with late_payments; PAID => amount 0 and a future due date; UNPAID amount = monthly charges x months outstanding.",
        "on_time_payment_ratio": "DERIVED: 1 - late_payments / min(max(tenure,1),36).",
        "marketing_consent": "SYNTHETIC: 85% consented.",
        "last_contacted_date": "SYNTHETIC: 60% contacted within the last 1-120 days.",
    }
