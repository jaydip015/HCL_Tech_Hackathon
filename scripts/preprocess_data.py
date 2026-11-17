"""Stage 1: raw CSV -> data/processed/customers_clean.csv (chunked)."""
import _bootstrap  # noqa: F401
import argparse
import json

from config import get_settings
from modules.data_engineering.ingestion import preprocess_file

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    s = get_settings()
    out = s.data_dir / "processed" / "customers_clean.csv"
    stats = preprocess_file(a.csv, out, s, a.limit)
    print(json.dumps(stats, indent=2))
    print("Written:", out)
