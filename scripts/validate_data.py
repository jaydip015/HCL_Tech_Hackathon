"""Data validation + profiling: checks the CSV header against the mapping layer and writes
reports/dataset_profile.md (columns, dtypes, nulls, duplicates, categorical values)."""
import _bootstrap  # noqa: F401
import argparse
import json

from config import get_settings
from modules.data_engineering.data_loader import check_mapping, inspect_csv, profile_dataset, profile_to_markdown

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--limit", type=int, default=None, help="profile only the first N rows")
    a = ap.parse_args()
    s = get_settings()
    mapping = s.data_mapping
    insp = inspect_csv(a.csv, mapping)
    print("Columns found:", insp.columns)
    print("Mapped columns missing from file:", insp.missing_mapped_columns or "none")
    print("Unmapped (ignored) columns:", insp.unmapped_columns or "none")
    check_mapping(a.csv, mapping)  # raises if customer_id is missing
    prof = profile_dataset(a.csv, limit=a.limit)
    out = s.reports_dir / "dataset_profile.md"
    out.write_text(profile_to_markdown(prof, mapping), encoding="utf-8")
    (s.reports_dir / "dataset_profile.json").write_text(json.dumps(prof, indent=2, default=str), encoding="utf-8")
    print(f"Rows: {prof['rows']:,} | duplicate IDs: {prof['duplicate_customer_ids']:,}")
    print("Profile written to", out)
