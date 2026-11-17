"""Dataset inspection and chunked loading (Person 1).

Never assumes the CSV layout: `inspect_csv` reads the real header and a sample, and
`check_mapping` reports any mapped column missing from the file before ingestion starts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


class MappingError(ValueError):
    """Raised when the CSV does not contain the columns the mapping layer expects."""


@dataclass
class CsvInspection:
    path: str
    columns: list[str]
    dtypes: dict[str, str]
    sample_rows: list[dict[str, Any]]
    missing_mapped_columns: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)


def read_header(path: Path | str) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def inspect_csv(path: Path | str, mapping: dict[str, Any], sample_size: int = 5) -> CsvInspection:
    sample = pd.read_csv(path, nrows=max(sample_size, 1000))
    cols = list(sample.columns)
    column_map: dict[str, str] = mapping.get("column_map", {})
    dropped = set(mapping.get("dropped_columns", []))
    return CsvInspection(
        path=str(path),
        columns=cols,
        dtypes={c: str(t) for c, t in sample.dtypes.items()},
        sample_rows=sample.head(sample_size).to_dict(orient="records"),
        missing_mapped_columns=[c for c in column_map if c not in cols],
        unmapped_columns=[c for c in cols if c not in column_map and c not in dropped],
    )


def check_mapping(path: Path | str, mapping: dict[str, Any], required: tuple[str, ...] = ("customer_id",)) -> list[str]:
    """Return mapped-but-missing columns; raise if a required one is absent."""
    header = read_header(path)
    column_map: dict[str, str] = mapping.get("column_map", {})
    missing = [c for c in column_map if c not in header]
    missing_required = [src for src, dst in column_map.items() if dst in required and src not in header]
    if missing_required:
        raise MappingError(
            f"CSV is missing required column(s) {missing_required}. Header found: {header}. "
            "Update config/data_mapping.yaml to match the file."
        )
    return missing


def iter_chunks(path: Path | str, chunk_size: int = 100_000, limit: int | None = None) -> Iterator[pd.DataFrame]:
    """Stream the CSV in chunks so a 1M-row file never sits fully in memory."""
    read = 0
    for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
        if limit is not None:
            remaining = limit - read
            if remaining <= 0:
                break
            chunk = chunk.head(remaining)
        read += len(chunk)
        yield chunk


def profile_dataset(path: Path | str, chunk_size: int = 100_000, limit: int | None = None,
                    max_categories: int = 25) -> dict[str, Any]:
    """Streaming dataset profile: rows, dtypes, nulls, duplicate IDs, categorical values."""
    rows = 0
    nulls: dict[str, int] = {}
    dtypes: dict[str, str] = {}
    categories: dict[str, dict[str, int]] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    seen_ids: set[int] = set()
    duplicate_ids = 0
    for chunk in iter_chunks(path, chunk_size, limit):
        rows += len(chunk)
        if not dtypes:
            dtypes = {c: str(t) for c, t in chunk.dtypes.items()}
        for c, n in chunk.isna().sum().items():
            nulls[c] = nulls.get(c, 0) + int(n)
        if "customer_id" in chunk.columns:
            hashed = pd.util.hash_pandas_object(chunk["customer_id"].astype(str), index=False)
            for h in hashed.tolist():
                if h in seen_ids:
                    duplicate_ids += 1
                else:
                    seen_ids.add(h)
        for c in chunk.columns:
            s = chunk[c]
            if s.dtype == object:
                vc = s.value_counts(dropna=True)
                if c == "customer_id" or len(vc) > max_categories * 4:
                    continue
                bucket = categories.setdefault(c, {})
                for k, v in vc.items():
                    bucket[str(k)] = bucket.get(str(k), 0) + int(v)
            elif pd.api.types.is_numeric_dtype(s):
                st = numeric_stats.setdefault(c, {"min": float("inf"), "max": float("-inf"), "sum": 0.0, "n": 0})
                valid = s.dropna()
                if len(valid):
                    st["min"] = min(st["min"], float(valid.min()))
                    st["max"] = max(st["max"], float(valid.max()))
                    st["sum"] += float(valid.sum())
                    st["n"] += int(len(valid))
    for st in numeric_stats.values():
        st["mean"] = round(st["sum"] / st["n"], 4) if st["n"] else None
        st.pop("sum")
    categories = {c: dict(sorted(v.items(), key=lambda kv: -kv[1])[:max_categories]) for c, v in categories.items()}
    return {
        "path": str(path),
        "rows": rows,
        "columns": list(dtypes.keys()),
        "dtypes": dtypes,
        "null_counts": nulls,
        "duplicate_customer_ids": duplicate_ids,
        "categorical_values": categories,
        "numeric_stats": numeric_stats,
    }


def profile_to_markdown(profile: dict[str, Any], mapping: dict[str, Any] | None = None) -> str:
    lines = [
        "# Dataset profiling report",
        "",
        f"- File: `{profile['path']}`",
        f"- Rows profiled: **{profile['rows']:,}**",
        f"- Columns: **{len(profile['columns'])}**",
        f"- Duplicate customer IDs: **{profile['duplicate_customer_ids']:,}**",
        "",
        "## Columns",
        "",
        "| Column | dtype | Nulls | Null % | Mapping |",
        "|---|---|---|---|---|",
    ]
    cmap = (mapping or {}).get("column_map", {})
    dropped = set((mapping or {}).get("dropped_columns", []))
    for c in profile["columns"]:
        n = profile["null_counts"].get(c, 0)
        pct = (100 * n / profile["rows"]) if profile["rows"] else 0
        target = cmap.get(c) or ("DROPPED (protected/unused)" if c in dropped else "unmapped")
        lines.append(f"| {c} | {profile['dtypes'].get(c, '')} | {n:,} | {pct:.2f}% | {target} |")
    lines += ["", "## Numeric columns", "", "| Column | Min | Max | Mean |", "|---|---|---|---|"]
    for c, st in profile["numeric_stats"].items():
        lines.append(f"| {c} | {st['min']} | {st['max']} | {st['mean']} |")
    lines += ["", "## Categorical values (top values)", ""]
    for c, vals in profile["categorical_values"].items():
        lines.append(f"- **{c}**: " + ", ".join(f"{k} ({v:,})" for k, v in vals.items()))
    return "\n".join(lines) + "\n"
