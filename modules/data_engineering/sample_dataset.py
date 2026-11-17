"""LOCAL STAND-IN for the Kaggle file (Person 1).

Generates a CSV with the same 32 columns as `customer_churn_1m.csv` so the whole pipeline can
be run and tested without Kaggle access. Rows are random and are NOT Kaggle data; they are
loaded with data_source='sample' so the UI never presents them as the real dataset.
Includes a few deliberately dirty rows (bad numbers, duplicate ID, missing ID) to exercise cleaning.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

KAGGLE_COLUMNS = [
    "customer_id", "signup_date", "age", "gender", "annual_income", "education", "marital_status",
    "dependents", "tenure", "contract", "payment_method", "paperless_billing", "senior_citizen",
    "monthlycharges", "totalcharges", "num_services", "has_phone_service", "has_internet_service",
    "has_online_security", "has_online_backup", "has_device_protection", "has_tech_support",
    "has_streaming_tv", "has_streaming_movies", "customer_satisfaction", "num_complaints",
    "num_service_calls", "late_payments", "avg_monthly_gb", "days_since_last_interaction",
    "credit_score", "churn",
]


def make_sample_csv(path: Path | str, n: int = 5000, seed: int = 7, dirty: bool = True) -> Path:
    rng = np.random.default_rng(seed)
    tenure = rng.integers(0, 73, n)
    monthly = np.round(rng.uniform(20, 120, n), 2)
    late = rng.poisson(0.6, n)
    days_since = np.where(rng.random(n) < 0.12, rng.integers(90, 240, n), rng.integers(0, 60, n))
    churn = (rng.random(n) < (0.12 + 0.25 * (days_since >= 90))).astype(int)
    services = rng.integers(1, 8, n)
    flags = {c: rng.integers(0, 2, n) for c in KAGGLE_COLUMNS if c.startswith("has_")}
    base = datetime(2026, 1, 1)
    df = pd.DataFrame({
        "customer_id": [f"CUST{str(i + 1).zfill(10)}" for i in range(n)],
        "signup_date": [(base - timedelta(days=int(t * 30))).strftime("%Y-%m-%d %H:%M:%S") for t in tenure],
        "age": rng.integers(18, 80, n),
        "gender": rng.choice(["Male", "Female"], n),
        "annual_income": np.round(rng.normal(60000, 15000, n), 2),
        "education": rng.choice(["high_school", "college", "bachelor", "master", "phd"], n),
        "marital_status": rng.choice(["single", "married", "divorced"], n),
        "dependents": rng.integers(0, 4, n),
        "tenure": tenure,
        "contract": rng.choice(["month_to_month", "one_year", "two_year"], n, p=[0.5, 0.3, 0.2]),
        "payment_method": rng.choice(["electronic_check", "mailed_check", "bank_transfer", "credit_card"], n),
        "paperless_billing": rng.choice(["Yes", "No"], n),
        "senior_citizen": (rng.random(n) < 0.16).astype(int),
        "monthlycharges": monthly,
        "totalcharges": np.round(monthly * np.maximum(tenure, 1) * rng.uniform(0.95, 1.05, n), 2),
        "num_services": services,
        **flags,
        "customer_satisfaction": rng.integers(1, 11, n).astype(float),
        "num_complaints": rng.poisson(0.3, n).astype(float),
        "num_service_calls": rng.poisson(1.2, n),
        "late_payments": late,
        "avg_monthly_gb": np.round(rng.gamma(2.0, 30.0, n), 2),
        "days_since_last_interaction": days_since,
        "credit_score": np.where(rng.random(n) < 0.05, np.nan, rng.integers(300, 850, n)),
        "churn": churn,
    })[KAGGLE_COLUMNS]
    if dirty and n >= 10:
        df["monthlycharges"] = df["monthlycharges"].astype(object)
        df["customer_id"] = df["customer_id"].astype(object)
        df.loc[3, "monthlycharges"] = "not_a_number"
        df.loc[4, "tenure"] = -5
        df.loc[5, "totalcharges"] = np.nan
        df.loc[6, "customer_id"] = None
        df = pd.concat([df, df.iloc[[1]]], ignore_index=True)  # duplicate ID
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
