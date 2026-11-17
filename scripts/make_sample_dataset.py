"""Create a LOCAL STAND-IN CSV with the Kaggle file's 32 columns (random rows, not Kaggle data)."""
import _bootstrap  # noqa: F401
import argparse

from config import get_settings
from modules.data_engineering.sample_dataset import make_sample_csv

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or get_settings().data_dir / "samples" / "sample_customers_kaggle_schema.csv"
    print("Written:", make_sample_csv(out, n=a.rows))
