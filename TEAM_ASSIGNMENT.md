# Team assignment

Four owners, each with a separate area of the code and stable shared contracts (`backend/schemas/models.py`). A module may call another owner's public functions, but it must never re-implement or bypass them. For example, generation receives the validator as an injected function and cannot skip it.

| Owner | Scope | Code | Tests | Status |
|---|---|---|---|---|
| **Person 1: Data engineering, profiles and backend data APIs** | Dataset ingestion, mapping, cleaning, duplicate and missing-value handling, deterministic synthetic enrichment, demo customers, profile builder with the data-quality gate, SQLite repository, customer search and pagination, customer API | `modules/data_engineering/*`, `modules/profile_builder/*`, `backend/api/customer_routes.py`, `config/data_mapping.yaml`, `scripts/download_dataset.py, validate_data.py, preprocess_data.py, generate_synthetic_data.py, load_database.py, make_sample_dataset.py` | `test_data.py`, `test_profiles.py` | Done, integrated |
| **Person 2: RAG, policy engine and policy Q&A** | 9 synthetic policy docs, loader, section chunking with injection stripping, embeddings (Sentence Transformers or TF-IDF), vector store (Chroma or local), retriever with metadata filters, versioned policy registry, segmentation engine (policy rules), customer-specific policy Q&A | `knowledge_base/policies/*`, `modules/rag/*`, `modules/policy/policy_manager.py`, `modules/segmentation/*`, `policies/segmentation.yaml`, `backend/api/policy_routes.py`, `scripts/ingest_policies.py` | `test_rag.py`, `test_segmentation.py` | Done, integrated |
| **Person 3: Offers, strategy and LLM email generation** | Approved offer catalog, eligibility rules, strategy selector with suppression, verified-facts builder, prompt manager and versioned prompts, LLM client (Claude, OpenAI-compatible, none), templates, structured output, repair, format retry and static fallback, offline simulator and fault injection | `policies/offers.yaml, communication.yaml, payment_reminders.yaml`, `modules/offers/*`, `modules/strategy/*`, `modules/generation/*`, `prompts/*`, `knowledge_base/templates/*`, `backend/api/generation_routes.py` | `test_offers.py`, `test_strategy.py`, `test_generation.py` | Done, integrated |
| **Person 4: Validation, review, delivery, audit, deployment and evaluation** | 16+ deterministic validators, advisory tone judge, draft repository, review workflow, pre-send gate, mock email, audit trail with redaction, metrics, evaluation harness, Streamlit app, FastAPI app, integration layer | `modules/validation/*`, `modules/review/*`, `modules/email/*`, `modules/audit/*`, `modules/evaluation/*`, `backend/services/*`, `backend/api/review_routes.py`, `main.py`, `app.py`, `frontend/*`, `policies/privacy.yaml`, `scripts/run_evaluation.py, demo_e2e.py, setup_all.py` | `test_validation.py`, `test_review.py`, `test_mock_email.py`, `test_api.py`, `test_frontend_smoke.py`, `test_integration.py` | Done, integrated |

## Shared ownership rules

- **Changing a model in `backend/schemas/models.py`** affects every owner. Update `API_CONTRACTS.md` and notify the others.
- **Business rules belong in `policies/*.yaml`, not in code.** The owner of the YAML file approves changes to it.
- **Before merging**, run `python -m pytest -q` (all tests must pass) and `python scripts/run_evaluation.py` (no metric may regress).

## Demo responsibilities

| Person | Scenarios presented |
|---|---|
| P1 | Data loading and profile provenance, contradictory data (H) |
| P2 | Classification evidence and policy chat: why LOYAL, why blocked |
| P3 | Loyal (A), declining (B), dormant (C), expired offer recomputed (F) |
| P4 | Overdue stages (D), no consent (E), hallucinated amount caught (G), review, mock send and audit trail |
