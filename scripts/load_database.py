"""Stage 3: load customers into SQLite.

  python scripts/load_database.py --csv data/raw/customer_churn_1m.csv   # full pipeline from raw (chunked)
  python scripts/load_database.py --enriched data/synthetic/customers_enriched.csv
  python scripts/load_database.py --sample 5000                           # local stand-in data
Always (re)loads the labelled demo customers. Use --classify to batch-classify for dashboards.
"""
import _bootstrap  # noqa: F401
import argparse
import json

from backend.services.bootstrap import classify_all, load_csv, load_demo_customers, load_sample_dataset
from backend.services.container import build_container
from modules.data_engineering.ingestion import load_enriched_file

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--csv")
    g.add_argument("--enriched")
    g.add_argument("--sample", type=int)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--classify", action="store_true")
    a = ap.parse_args()
    c = build_container()
    if a.csv:
        print(json.dumps(load_csv(c, a.csv, a.limit), indent=2))
    elif a.enriched:
        print("Loaded", load_enriched_file(a.enriched, c.customers))
    elif a.sample:
        print(json.dumps(load_sample_dataset(c, a.sample), indent=2))
    labels = load_demo_customers(c)
    print(f"Loaded {len(labels)} labelled demo customers.")
    if a.classify:
        print("Segment counts:", classify_all(c, progress=lambda n: print(f"  classified {n:,}", end="\r")))
    print("Customers by source:", c.customers.source_counts())
