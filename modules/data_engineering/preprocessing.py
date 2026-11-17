"""Cleaning and normalisation of raw dataset chunks (Person 1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class CleaningStats:
    rows_in: int = 0
    rows_out: int = 0
    dropped_missing_id: int = 0
    duplicates_dropped: int = 0
    coerced_to_null: dict[str, int] = field(default_factory=dict)
    total_charges_imputed: int = 0
    protected_columns_dropped: list[str] = field(default_factory=list)

    def merge(self, other: "CleaningStats") -> None:
        self.rows_in += other.rows_in
        self.rows_out += other.rows_out
        self.dropped_missing_id += other.dropped_missing_id
        self.duplicates_dropped += other.duplicates_dropped
        self.total_charges_imputed += other.total_charges_imputed
        for k, v in other.coerced_to_null.items():
            self.coerced_to_null[k] = self.coerced_to_null.get(k, 0) + v
        for c in other.protected_columns_dropped:
            if c not in self.protected_columns_dropped:
                self.protected_columns_dropped.append(c)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def clean_chunk(raw: pd.DataFrame, mapping: dict[str, Any], seen_ids: set[str] | None = None) -> tuple[pd.DataFrame, CleaningStats]:
    """Map source columns to internal names, drop protected columns, coerce types,
    handle missing values and remove duplicate customer IDs (also across chunks via seen_ids)."""
    stats = CleaningStats(rows_in=len(raw))
    column_map: dict[str, str] = mapping.get("column_map", {})
    dropped_cfg = set(mapping.get("dropped_columns", []))

    stats.protected_columns_dropped = [c for c in raw.columns if c in dropped_cfg]
    keep = [c for c in raw.columns if c in column_map]
    df = raw[keep].rename(columns=column_map).copy()

    # Identifier
    df["customer_id"] = df["customer_id"].astype("string").str.strip()
    missing_id = df["customer_id"].isna() | (df["customer_id"] == "")
    stats.dropped_missing_id = int(missing_id.sum())
    df = df[~missing_id]

    # Duplicates within the chunk and against earlier chunks
    before = len(df)
    df = df.drop_duplicates(subset="customer_id", keep="first")
    if seen_ids is not None:
        dup_prev = df["customer_id"].isin(seen_ids)
        df = df[~dup_prev]
        seen_ids.update(df["customer_id"].tolist())
    stats.duplicates_dropped = before - len(df)

    # Numeric coercion (invalid strings -> NaN, counted)
    for col in mapping.get("numeric_fields", []):
        if col in df.columns:
            original_nulls = int(df[col].isna().sum())
            df[col] = pd.to_numeric(df[col], errors="coerce")
            coerced = int(df[col].isna().sum()) - original_nulls
            if coerced:
                stats.coerced_to_null[col] = coerced

    # Impossible values -> null (treated as missing evidence later, never guessed)
    for col in ("tenure_months", "monthly_charges", "total_charges", "avg_monthly_gb",
                "days_since_last_interaction", "late_payments", "customer_service_calls"):
        if col in df.columns:
            bad = df[col] < 0
            if bad.any():
                stats.coerced_to_null[col] = stats.coerced_to_null.get(col, 0) + int(bad.sum())
                df.loc[bad, col] = pd.NA

    # Missing total charges: the one documented imputation (monthly * tenure)
    if {"total_charges", "monthly_charges", "tenure_months"} <= set(df.columns):
        need = df["total_charges"].isna() & df["monthly_charges"].notna() & df["tenure_months"].notna()
        df.loc[need, "total_charges"] = (df.loc[need, "monthly_charges"] * df.loc[need, "tenure_months"]).round(2)
        stats.total_charges_imputed = int(need.sum())

    # Categorical normalisation
    for col, vmap in (mapping.get("value_maps") or {}).items():
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().map(lambda v: vmap.get(v, vmap.get(str(v).lower(), v)) if pd.notna(v) else v)

    for col in ("tenure_months", "num_services", "customer_service_calls", "late_payments",
                "days_since_last_interaction", "churn_status"):
        if col in df.columns:
            df[col] = df[col].round().astype("Int64")

    stats.rows_out = len(df)
    return df.reset_index(drop=True), stats
