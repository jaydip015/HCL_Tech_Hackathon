"""End-to-end ingestion: CSV -> clean -> enrich -> SQLite, chunk by chunk (Person 1)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from backend.database.db import now_iso
from config import Settings
from modules.data_engineering.data_loader import check_mapping, iter_chunks
from modules.data_engineering.preprocessing import CleaningStats, clean_chunk
from modules.data_engineering.synthetic_generator import enrich_chunk
from modules.profile_builder.customer_repository import CUSTOMER_COLUMNS, CustomerRepository

log = logging.getLogger(__name__)


def ingest_csv(path: Path | str, settings: Settings, repo: CustomerRepository, *, source: str = "kaggle",
               limit: int | None = None, chunk_size: int | None = None,
               progress: Callable[[int], None] | None = None) -> dict[str, Any]:
    mapping = settings.data_mapping
    missing = check_mapping(path, mapping)
    chunk_size = chunk_size or int(mapping.get("dataset", {}).get("chunk_size", 100_000))
    support = settings.communication["support"]["phone"]
    seen: set[str] = set()
    total = CleaningStats()
    loaded = 0
    for i, raw in enumerate(iter_chunks(path, chunk_size, limit)):
        clean, stats = clean_chunk(raw, mapping, seen)
        total.merge(stats)
        enriched = enrich_chunk(clean, settings.as_of_date, settings.synthetic_seed, support)
        enriched["data_source"] = source
        enriched["ingested_at"] = now_iso()
        records = dataframe_to_records(enriched)
        repo.upsert_many(records)
        loaded += len(records)
        log.info("chunk %s: %s rows loaded", i, len(records))
        if progress:
            progress(loaded)
    return {"loaded": loaded, "missing_mapped_columns": missing, "cleaning": total.as_dict(), "source": source}


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    df = df.reindex(columns=CUSTOMER_COLUMNS)
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


# ---------------------------------------------------------------- staged pipeline (scripts)
def preprocess_file(raw_path: Path | str, out_path: Path | str, settings: Settings, limit: int | None = None) -> dict[str, Any]:
    """Stage 1: raw Kaggle CSV -> cleaned CSV (mapped names, protected columns dropped)."""
    mapping = settings.data_mapping
    check_mapping(raw_path, mapping)
    chunk_size = int(mapping.get("dataset", {}).get("chunk_size", 100_000))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    total = CleaningStats()
    for i, raw in enumerate(iter_chunks(raw_path, chunk_size, limit)):
        clean, stats = clean_chunk(raw, mapping, seen)
        total.merge(stats)
        clean.to_csv(out_path, mode="w" if i == 0 else "a", header=i == 0, index=False)
    return total.as_dict()


def enrich_file(clean_path: Path | str, out_path: Path | str, settings: Settings, source: str = "kaggle") -> int:
    """Stage 2: cleaned CSV -> enriched CSV with clearly-labelled synthetic fields."""
    support = settings.communication["support"]["phone"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, chunk in enumerate(pd.read_csv(clean_path, chunksize=100_000, dtype={"customer_id": str})):
        enriched = enrich_chunk(chunk, settings.as_of_date, settings.synthetic_seed, support)
        enriched["data_source"] = source
        enriched.to_csv(out_path, mode="w" if i == 0 else "a", header=i == 0, index=False)
        n += len(enriched)
    return n


def load_enriched_file(path: Path | str, repo: CustomerRepository) -> int:
    """Stage 3: enriched CSV -> SQLite."""
    n = 0
    for chunk in pd.read_csv(path, chunksize=50_000, dtype={"customer_id": str}):
        chunk["ingested_at"] = now_iso()
        n += repo.upsert_many(dataframe_to_records(chunk))
    return n
