"""Download the Kaggle 'Customer Churn Prediction Dataset 1M' into data/raw/.

Needs the `kaggle` package and credentials (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY).
Without them, it prints manual download steps. The app also accepts a manual CSV upload.
"""
import _bootstrap  # noqa: F401
import sys

from config import get_settings


def main() -> int:
    s = get_settings()
    slug = s.data_mapping["dataset"]["kaggle_slug"]
    raw = s.data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore

        api = KaggleApi()
        api.authenticate()
        print(f"Downloading {slug} to {raw} ...")
        api.dataset_download_files(slug, path=str(raw), unzip=True)
        print("Done. Files:", [p.name for p in raw.iterdir()])
        return 0
    except Exception as exc:
        print(f"Automatic download unavailable ({exc}).\n")
        print("Manual steps:")
        print(f"  1. Open https://www.kaggle.com/datasets/{slug}")
        print("  2. Click Download, unzip, and copy customer_churn_1m.csv to:")
        print(f"     {raw / 'customer_churn_1m.csv'}")
        print("  3. Run: python scripts/load_database.py --csv data/raw/customer_churn_1m.csv")
        print("  Or upload the CSV from the Streamlit 'Customer Explorer' page.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
