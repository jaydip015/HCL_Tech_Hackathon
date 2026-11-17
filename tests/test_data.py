import pandas as pd
import pytest

from modules.data_engineering.data_loader import MappingError, check_mapping, inspect_csv, profile_dataset
from modules.data_engineering.ingestion import ingest_csv
from modules.data_engineering.preprocessing import clean_chunk
from modules.data_engineering.sample_dataset import make_sample_csv
from modules.data_engineering.synthetic_generator import enrich_chunk


@pytest.fixture
def sample_csv(tmp_path):
    return make_sample_csv(tmp_path / "raw.csv", n=600)


def test_inspect_and_mapping(sample_csv, settings):
    insp = inspect_csv(sample_csv, settings.data_mapping)
    assert "customer_id" in insp.columns and len(insp.columns) == 32
    assert insp.missing_mapped_columns == []
    assert check_mapping(sample_csv, settings.data_mapping) == []


def test_mapping_fails_loudly_without_customer_id(tmp_path, settings):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"id": [1], "tenure": [3]}).to_csv(p, index=False)
    with pytest.raises(MappingError):
        check_mapping(p, settings.data_mapping)


def test_cleaning_drops_protected_dupes_and_bad_values(sample_csv, settings):
    raw = pd.read_csv(sample_csv)
    clean, stats = clean_chunk(raw, settings.data_mapping, set())
    for col in ("gender", "age", "senior_citizen", "annual_income", "credit_score", "SeniorCitizen"):
        assert col not in clean.columns
    assert stats.dropped_missing_id == 1 and stats.duplicates_dropped == 1
    assert stats.coerced_to_null.get("monthly_charges") == 1   # "not_a_number"
    assert stats.coerced_to_null.get("tenure_months") == 1     # negative tenure
    assert clean["customer_id"].is_unique
    assert set(clean["contract_type"].dropna().unique()) <= {"Month-to-month", "One year", "Two year"}


def test_profile_dataset_counts(sample_csv):
    prof = profile_dataset(sample_csv, chunk_size=100)
    assert prof["rows"] == 601 and prof["duplicate_customer_ids"] >= 1
    assert prof["null_counts"]["customer_id"] == 1


def test_synthetic_is_deterministic_and_chunk_independent(sample_csv, settings):
    clean, _ = clean_chunk(pd.read_csv(sample_csv), settings.data_mapping, set())
    a = enrich_chunk(clean, settings.as_of_date, 42, "x")
    b = pd.concat([enrich_chunk(clean.iloc[:200], settings.as_of_date, 42, "x"),
                   enrich_chunk(clean.iloc[200:], settings.as_of_date, 42, "x")])
    cols = ["customer_name", "payment_status", "amount_due", "bill_due_date", "marketing_consent", "usage_last_3m"]
    pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].reset_index(drop=True))
    c = enrich_chunk(clean, settings.as_of_date, 7, "x")
    assert not a["customer_name"].equals(c["customer_name"])  # seed changes values


def test_synthetic_relationships_are_consistent(sample_csv, settings):
    clean, _ = clean_chunk(pd.read_csv(sample_csv), settings.data_mapping, set())
    e = enrich_chunk(clean, settings.as_of_date, 42, "x")
    paid = e[e["payment_status"] == "PAID"]
    assert (paid["amount_due"] == 0).all()
    assert (pd.to_datetime(paid["bill_due_date"]).dt.date > settings.as_of_date).all()
    unpaid = e[e["payment_status"] == "UNPAID"]
    assert (unpaid["amount_due"] > 0).all()
    assert e["email_address"].str.endswith("@example.com").all()


def test_ingest_to_sqlite_never_stores_protected(sample_csv, container):
    res = ingest_csv(sample_csv, container.settings, container.customers, source="sample", chunk_size=250)
    assert res["loaded"] == 599
    cols = {r["name"] for r in container.db.query("PRAGMA table_info(customers)")}
    assert not cols & {"gender", "age", "senior_citizen", "annual_income", "credit_score", "marital_status"}
    assert container.customers.count(source="sample") == 599
    page = container.customers.search(source="sample", limit=10, offset=10)
    assert len(page) == 10
