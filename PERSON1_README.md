# Person 1: Data engineering, customer profiles and customer APIs

> These are **copies** for reading and study. The application still runs from the original files in the
> project root; editing a file here changes nothing in the running app. Make real changes in the
> original location (same relative path) and run `python -m pytest -q` from the project root.

## What this person owns

Load the 1M-row Kaggle churn CSV in chunks, clean it, drop protected attributes, add clearly labelled synthetic business fields, build verified CustomerProfile objects with a data-quality gate, store them in SQLite and expose search and the customer API.

- **Hands off:** CustomerProfile (+ DataIssue) to Persons 2, 3 and 4
- **Demo:** Data loading and provenance, Customer Explorer, scenario H (contradictory payment status)
- **Full guide:** `../shared/TEAM_HANDBOOK.md` (section 3: reading order, concepts, judge questions)

## UI pages that show this work

- `frontend/pages/1_executive_dashboard.py` (data loading panel)
- `frontend/pages/2_customer_explorer.py`

The UI pages are owned and maintained by Person 4; they call this person's modules.

## Shared files this person must also read (in `../shared/`)

- `backend/schemas/models.py`: the contracts passed between all four people
- `config.py`, `CLAUDE.md`, `README.md`, `TEAM_HANDBOOK.md`, `API_CONTRACTS.md`, `INTEGRATION_GUIDE.md`
- `tests/conftest.py`, `tests/fakes.py`: test fixtures used by this person's tests

## Files in this folder (28)

**Project root** - Top-level files

- `DATA_DICTIONARY.md`

**backend/** - API routes, services, database

- `backend/api/customer_routes.py`

**config/** - Technical configuration

- `config/data_mapping.yaml`

**data/** - Data folders (large files not copied)

- `data/processed/.gitkeep`
- `data/raw/.gitkeep`
- `data/samples/.gitkeep`
- `data/samples/sample_customers_kaggle_schema.csv`
- `data/synthetic/.gitkeep`

**modules/** - Business logic

- `modules/data_engineering/__init__.py`
- `modules/data_engineering/data_loader.py`
- `modules/data_engineering/demo_customers.py`
- `modules/data_engineering/ingestion.py`
- `modules/data_engineering/preprocessing.py`
- `modules/data_engineering/sample_dataset.py`
- `modules/data_engineering/synthetic_generator.py`
- `modules/profile_builder/__init__.py`
- `modules/profile_builder/customer_repository.py`
- `modules/profile_builder/profile_builder.py`

**reports/** - Generated reports

- `reports/dataset_profile.json`
- `reports/dataset_profile.md`

**scripts/** - Command-line scripts

- `scripts/download_dataset.py`
- `scripts/generate_synthetic_data.py`
- `scripts/load_database.py`
- `scripts/make_sample_dataset.py`
- `scripts/preprocess_data.py`
- `scripts/validate_data.py`

**tests/** - Automated tests

- `tests/test_data.py`
- `tests/test_profiles.py`
