"""Stage 2: cleaned CSV -> data/synthetic/customers_enriched.csv (deterministic, seed from SYNTHETIC_SEED)."""
import _bootstrap  # noqa: F401
import argparse

from config import get_settings
from modules.data_engineering.ingestion import enrich_file
from modules.data_engineering.synthetic_generator import describe_rules

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean-csv", default=None)
    ap.add_argument("--source", default="kaggle", help="label stored in data_source (kaggle|sample)")
    a = ap.parse_args()
    s = get_settings()
    src = a.clean_csv or s.data_dir / "processed" / "customers_clean.csv"
    out = s.data_dir / "synthetic" / "customers_enriched.csv"
    n = enrich_file(src, out, s, a.source)
    print(f"Enriched {n:,} rows with seed {s.synthetic_seed} (as of {s.as_of_date}). Rules:")
    for k, v in describe_rules().items():
        print(f"  - {k}: {v}")
    print("Written:", out)
