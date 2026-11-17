"""One command to get a working demo database.

Loads data/raw/customer_churn_1m.csv if present (use --limit for a quick start), otherwise
generates the local stand-in sample. Then loads demo customers, classifies, indexes policies.
"""
import _bootstrap  # noqa: F401
import argparse

from backend.services.bootstrap import classify_all, load_csv, load_demo_customers, load_sample_dataset
from backend.services.container import build_container

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50000, help="rows to load from the Kaggle CSV (0 = all)")
    ap.add_argument("--sample-rows", type=int, default=5000)
    a = ap.parse_args()
    c = build_container()
    raw = c.settings.data_dir / "raw" / c.settings.data_mapping["dataset"]["expected_file"]
    if raw.exists():
        print(f"Loading Kaggle CSV {raw} (limit={a.limit or 'all'}) ...")
        print(load_csv(c, raw, a.limit or None))
    else:
        print("Kaggle CSV not found; generating the local stand-in sample (NOT Kaggle data) ...")
        print(load_sample_dataset(c, a.sample_rows))
    print(f"Demo customers: {len(load_demo_customers(c))}")
    print("Classifying ...", classify_all(c))
    print("Policy index:", c.retriever.stats())
    print("Ready. Start the UI with: streamlit run app.py")
