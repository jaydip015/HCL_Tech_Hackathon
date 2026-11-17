"""One-call setup helpers used by scripts, Streamlit and tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services.container import Container
from modules.data_engineering.demo_customers import demo_customers
from modules.data_engineering.ingestion import ingest_csv
from modules.data_engineering.sample_dataset import make_sample_csv
from modules.profile_builder.profile_builder import build_profile


def load_demo_customers(c: Container) -> dict[str, dict[str, Any]]:
    rows, labels = demo_customers(c.settings.as_of_date, c.settings.communication["support"]["phone"])
    c.customers.upsert_many(rows)
    return labels


def demo_labels(c: Container) -> dict[str, dict[str, Any]]:
    return demo_customers(c.settings.as_of_date, c.settings.communication["support"]["phone"])[1]


def load_sample_dataset(c: Container, n: int = 5000) -> dict[str, Any]:
    path = make_sample_csv(c.settings.data_dir / "samples" / "sample_customers_kaggle_schema.csv", n=n)
    return ingest_csv(path, c.settings, c.customers, source="sample")


def load_csv(c: Container, path: Path | str, limit: int | None = None, source: str = "kaggle") -> dict[str, Any]:
    return ingest_csv(path, c.settings, c.customers, source=source, limit=limit)


def classify_all(c: Container, source: str | None = None, batch_size: int = 20000, progress=None) -> dict[str, int]:
    """Batch classification for dashboards/filtering (no drafts are generated)."""
    counts: dict[str, int] = {}
    done = 0
    for rows in c.customers.iter_rows(batch_size, source):
        results = []
        for row in rows:
            seg = c.segmentation.classify(build_profile(row, c.settings))
            key = seg.primary_segment if seg.status == "CLASSIFIED" else "MANUAL_REVIEW"
            counts[key] = counts.get(key, 0) + 1
            results.append(seg.model_dump(mode="json"))
        c.customers.save_segments_bulk(results)
        done += len(rows)
        if progress:
            progress(done)
    return counts
