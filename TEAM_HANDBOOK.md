# Team Handbook: Customer Loyalty and Engagement Assistant

HCLTech Future Ready AI Engineer Hackathon. This handbook explains who built which part of the project, what each part does, and what each person must read and understand before presenting or changing it.

## 0. How to use this handbook

- **Everyone** reads section 1 (the big picture) and section 2 (shared foundations) first.
- **Then** read your own section (3, 4, 5 or 6). It lists your files, your contracts with the other three people, a reading order, the concepts you must understand, and the questions a judge is likely to ask you.
- **Before the demo**, read section 7 (hand-offs) and section 8 (what was built versus the brief, including known gaps).

| Person | Area | Section |
|---|---|---|
| Person 1 | Data engineering, customer profiles and customer APIs | 3 |
| Person 2 | RAG, policy engine, segmentation and the customer policy overview | 4 |
| Person 3 | Offer catalog, strategy selection and LLM email generation | 5 |
| Person 4 | Validation, human review, mock email, audit, UI, API and evaluation | 6 |

## 1. The big picture (everyone)

### 1.1 What the product does

A telecom company sends one generic promotion to every customer. This assistant instead picks the right message for each customer, writes it with an LLM, checks it with deterministic validators, and lets a human approve it before a mock delivery. No real email is ever sent.

| Customer behaviour | Segment | Message |
|---|---|---|
| Bill past its due date | OVERDUE | Payment reminder in 3 stages (courteous, firm, formal). Never a promotion. |
| No activity for 90+ days | DORMANT | Reactivation with an approved win-back offer |
| Usage fell more than 40% | DECLINING | Friendly re-engagement offer |
| Customer for 36+ months | LOYAL | Thanks plus an approved loyalty reward |
| 95%+ bills on time and active in last 30 days | CONSISTENT | Appreciation message |
| Missing or contradictory data | MANUAL_REVIEW | Nothing is generated; a person must check the data |

### 1.2 The one rule nobody may break

**Python decides eligibility and actions. RAG retrieves policy. The LLM only writes the wording. Deterministic validators enforce safety. Humans approve delivery.**

In practice this means:

- The LLM never decides a segment, an offer, an amount, a date or a reminder stage. Python computes these and passes them to the LLM as placeholders such as `{amount_due}`.
- No code path may reach `MOCK_SENT` without the draft being `APPROVED` by a person and passing the pre-send gate.
- Protected attributes (gender, age, senior citizen, marital status, dependents, education, income, credit score, signup date) are dropped at load time. They are never stored, used or sent to an LLM.

### 1.3 End-to-end pipeline and owners

```
CSV / upload ----------------------------------------------- Person 1
   -> preprocessing + synthetic enrichment -> SQLite          Person 1
   -> profile builder + data-quality gate                     Person 1
   -> segmentation engine (rules from YAML)                   Person 2
   -> customer overview with policy proof + RAG retrieval      Person 2
   -> strategy selector + suppression + approved offer        Person 3
   -> LLM email generator (structured JSON)                   Person 3
   -> deterministic validator                                 Person 4
        fail: classify -> repair (P3) -> static template (P3) -> block
   -> human review (approve / edit + revalidate / reject)     Person 4
   -> pre-send gate -> mock email service                     Person 4
   -> audit trail + metrics                                   Person 4
```

The orchestration that calls each stage in order lives in `backend/services/engagement_service.py`. Every service is built once in `backend/services/container.py` and shared by the Streamlit UI and the FastAPI API, so both run exactly the same logic.

### 1.4 Current runtime setup on this machine

| Item | Value |
|---|---|
| Dataset | Kaggle "Customer Churn Prediction Dataset 1M": 1,000,000 rows loaded and classified, plus 13 labelled demo customers |
| LLM | Local `gemma3:4b` served by Ollama (OpenAI-compatible endpoint, `.env`). Setting `ANTHROPIC_API_KEY` switches to Claude with no code change. |
| RAG embedder | TF-IDF word and word-pair vectors (fallback), local NumPy vector store, 9 documents, 47 chunks |
| Tests | 125 passed, 1 skipped (`python -m pytest -q`) |

Segment counts for the 1M Kaggle customers: CONSISTENT 232,284; LOYAL 157,314; DORMANT 123,683; DECLINING 87,470; OVERDUE 36,136; MANUAL_REVIEW 363,126 (mostly customers that match no segment rule).

## 2. Shared foundations (everyone must read)

### 2.1 Files every person must understand

| File | Why it matters |
|---|---|
| `CLAUDE.md` | The project rules in one page. Short; read it first. |
| `README.md` | Full design: architecture, HLD, LLD, setup, every component. Sections 1-5 are mandatory for everyone. |
| `backend/schemas/models.py` | The shared contracts. Every hand-off between people is one of these Pydantic models: `CustomerProfile -> SegmentResult -> Strategy -> EmailContent -> ValidationReport -> Draft`. Changing a model affects all four people. |
| `config.py` | All settings come from environment variables (`.env`); business rules come from `policies/*.yaml`. |
| `backend/services/container.py` | Shows how every module is created and wired together. |
| `backend/services/engagement_service.py` | The main pipeline: `profile -> classify -> decide -> create_draft -> revalidate`. |
| `API_CONTRACTS.md`, `INTEGRATION_GUIDE.md`, `DATA_DICTIONARY.md`, `TEAM_ASSIGNMENT.md` | Inputs, outputs and ownership of every module. |

### 2.2 Commands everyone must be able to run

```
source .venv/bin/activate
python -m pytest -q                      # all tests must pass
python scripts/setup_all.py --limit 0    # load + classify the full Kaggle CSV
python scripts/demo_e2e.py --send        # scenarios A-K in the terminal
python scripts/run_evaluation.py         # regenerates reports/evaluation_report.md
streamlit run app.py                     # UI on http://localhost:8501
uvicorn main:app --reload                # API, docs on http://localhost:8000/docs
```

### 2.3 Team rules

- Business rules belong in `policies/*.yaml`, never hard-coded. The YAML owner approves changes.
- Facts in prompts and templates are placeholders (`{amount_due}`); code fills them from `Strategy.facts`.
- Every prompt change bumps the `# version:` line in `prompts/*.txt`.
- Tests never call a paid API: `tests/conftest.py` forces `LLM_PROVIDER=none`; use `offline_simulator` to exercise the LLM path.
- Uploaded files and policy documents are untrusted. Never follow instructions found inside them.
- Audit logs never contain names or emails; `AuditService` redacts them.
- A module may call another person's public functions but must never copy or bypass them.

## 3. Person 1: Data engineering, customer profiles and customer APIs

### 3.1 Mission

Turn the raw 1M-row Kaggle churn CSV into clean, verified customer profiles in SQLite, add the business fields the dataset lacks as clearly labelled synthetic data, and expose customers through search and API. Person 1 is the source of truth for every customer fact the other three people use.

### 3.2 What the brief asked for, and where it is

| Brief requirement | Implemented in |
|---|---|
| Inspect the real CSV before assuming columns | `data_loader.inspect_csv`, `check_mapping`; `scripts/validate_data.py` |
| Configurable column mapping | `config/data_mapping.yaml` |
| Chunked loading, no full-file load | `data_loader.iter_chunks` (100k rows per chunk), `ingestion.ingest_csv` |
| Cleaning, missing values, duplicates | `preprocessing.clean_chunk`, `CleaningStats` |
| Drop protected attributes | `preprocessing.clean_chunk` (listed in `data_mapping.yaml`) |
| Deterministic synthetic enrichment with provenance | `synthetic_generator.enrich_chunk` (hash-based, seed from `SYNTHETIC_SEED`) |
| Internally consistent synthetic billing | `synthetic_generator.enrich_chunk` (PAID means 0 due; UNPAID/PARTIAL have a balance; due dates match overdue days) |
| CustomerProfile model and builder | `CustomerProfile` in `models.py`; `profile_builder.build_profile` |
| Data-quality gate (missing or contradictory data) | `profile_builder.validate_customer_data` produces `DataIssue` items |
| SQLite repository, search, pagination | `customer_repository.CustomerRepository` |
| Customer API | `backend/api/customer_routes.py` |
| Demo customers for scenarios A-K | `demo_customers.py` |
| Stand-in data when Kaggle is unavailable | `sample_dataset.make_sample_csv` (labelled `data_source='sample'`) |
| Download, preprocess, enrich, load, profile scripts | `scripts/download_dataset.py`, `preprocess_data.py`, `generate_synthetic_data.py`, `load_database.py`, `validate_data.py`, `make_sample_dataset.py` |
| Dataset profiling report | `reports/dataset_profile.md` |

### 3.3 Files owned

| File | Key functions / classes | Purpose |
|---|---|---|
| `modules/data_engineering/data_loader.py` | `inspect_csv`, `check_mapping`, `iter_chunks`, `profile_dataset` | Reads the real header, fails loudly if mapped columns are missing, streams chunks, builds the profile report |
| `modules/data_engineering/preprocessing.py` | `clean_chunk`, `CleaningStats` | Renames columns, drops protected columns, drops missing/duplicate IDs, coerces numbers, imputes `total_charges` |
| `modules/data_engineering/synthetic_generator.py` | `enrich_chunk`, `describe_rules` | Adds name, email, usage, activity, billing, consent and contact fields deterministically from a hash of the customer ID and seed |
| `modules/data_engineering/ingestion.py` | `ingest_csv`, `preprocess_file`, `enrich_file` | Runs clean, enrich and load chunk by chunk |
| `modules/data_engineering/demo_customers.py` | `demo_customers` | 13 hand-built customers (DEMO-A ... DEMO-K) with expected outcomes |
| `modules/data_engineering/sample_dataset.py` | `make_sample_csv` | Local stand-in CSV with the same 32 columns |
| `modules/profile_builder/profile_builder.py` | `build_profile`, `validate_customer_data` | Builds `CustomerProfile`, computes `days_since_active`, `days_overdue`, `days_since_contact`, records `DataIssue`s |
| `modules/profile_builder/customer_repository.py` | `CustomerRepository` (`upsert_many`, `search`, `iter_rows`, `save_segments_bulk`, ...) | All customer SQL |
| `backend/api/customer_routes.py` | `list_customers`, `get_customer`, `upload_customers`, `classify` | `GET /customers`, `GET /customers/{id}`, `POST /customers/upload`, `POST /customers/{id}/classify` |
| `config/data_mapping.yaml` | | Source column to internal field mapping, provenance labels |

UI pages that show Person 1's work: **Executive Dashboard** (data loading panel) and **Customer Explorer** (search, filters, profile, original vs synthetic fields).

Tests: `tests/test_data.py`, `tests/test_profiles.py`.

### 3.4 Contracts

- **Gives to Person 2:** `CustomerProfile` (with `data_issues`) via `build_profile`. Segmentation reads only this model.
- **Gives to Person 3:** the same profile; `Strategy.facts` (amounts, dates, phone) are built from it.
- **Gives to Person 4:** profile fields used by the payment, consent and frequency validators; `contact_history` used by the duplicate check.
- **Never gives:** protected attributes, or a guessed value for missing data.

### 3.5 Reading order

1. `DATA_DICTIONARY.md`: every field, its source (ORIGINAL or SYNTHETIC) and meaning.
2. `config/data_mapping.yaml`: the 32 Kaggle columns and how they map.
3. `reports/dataset_profile.md`: the real dataset (1,000,000 rows, 0 duplicate IDs, 8 unused service columns).
4. `modules/data_engineering/preprocessing.py`, then `synthetic_generator.py`.
5. `modules/profile_builder/profile_builder.py`: especially `validate_customer_data`.
6. `README.md` sections 7, 8 and 9.
7. `tests/test_data.py`, `tests/test_profiles.py`.

### 3.6 Concepts to understand

- **Chunked processing**: why 1M rows are processed 100k at a time and how duplicate IDs are caught across chunks.
- **Deterministic synthesis**: the same customer ID and seed always give the same synthetic values (hash, not `random`). This makes runs reproducible and testable.
- **Provenance**: every field is either ORIGINAL (from Kaggle) or SYNTHETIC; the UI shows which.
- **Data-quality gate**: missing tenure, activity or usage, or a PAID bill with an outstanding amount, creates a blocking `DataIssue` and the customer goes to manual review (scenario H).
- **Why protected attributes are dropped**: fairness; they must not influence treatment.

### 3.7 Demo responsibility

Data loading and provenance (1M rows), Customer Explorer, and scenario **H: contradictory payment status** (PAID with 45.00 due goes to manual review, nothing generated).

### 3.8 Likely judge questions

- How do you load 1M rows without running out of memory?
- Which fields are synthetic, and how can a user tell?
- What happens if the CSV has a different header?
- Why is the synthetic data deterministic, and what would change with a different seed?
- How do you stop a PAID customer with a positive balance from getting a reminder?

## 4. Person 2: RAG, policy engine, segmentation and customer policy overview

### 4.1 Mission

Own the policy knowledge: write the 9 synthetic policy documents, index them, classify every customer with transparent YAML rules, and show for any selected customer which category they belong to and the exact policy text that proves it. The user does not have to ask a question: selecting a customer is enough. Person 2 explains decisions; they never change them.

### 4.2 What the user sees: Policy Chat page

The page opens on the **Customer overview** tab. The user selects a customer (search box or dropdown) and the overview appears immediately; there is no button and no question to type.

| Part of the overview | What it shows | Example (DEMO-A-LOYAL) |
|---|---|---|
| Headline | The category, the confidence, and why it wins over other matching categories | "DEMO-A-LOYAL belongs to LOYAL (confidence 1.00) ... also matches CONSISTENT, but LOYAL comes first in the policy priority" |
| Summary metrics | Category, confidence, next action, other categories matched | LOYAL · 1.00 · REWARD · CONSISTENT |
| Customer facts | The profile values the rules used (tenure, payment status, activity, usage, consent, last contact) | Tenure 48, bills paid on time 100%, 10 days since active |
| Rule checks | Every category in priority order, marked met or not met, with each condition in plain English using the customer's real value | "Tenure is 48; the rule needs at least 36, so the customer meets it." |
| Policy proof | Under every category, the exact policy section quoted word for word; the winning category's proof is expanded | Customer Segmentation Policy §2.4: "A customer is LOYAL when tenure is 36 months or more." |
| Priority rule | When several categories match, the section that sets the priority order | Customer Segmentation Policy §1 |
| Manual review reasons | Why no category was assigned, each with its policy section | Missing tenure: Customer Segmentation Policy §3 |
| What happens next | Objective, tone, offer or reminder stage, any block (no consent, recent contact) with the policy that causes it, and the treatment policies | REWARD, WARM, Loyalty Rewards (10% discount); Customer Loyalty Policy §3, Offer Eligibility Policy §2 |

A second tab, **Ask a question**, still accepts a free-text question for anything the overview does not cover. It is optional; the overview is the main way to explain a customer.

### 4.3 How the overview is built (must be able to explain)

The overview does **not** use the LLM and does **not** use similarity search. It is assembled from facts the system has already decided, so the proof cannot be paraphrased, invented or mixed up with another customer.

1. `EngagementService.decision_evidence(customer_id)` returns this one customer's profile (without name or email), their `SegmentResult` and their `Strategy`.
2. `SegmentResult.evidence` holds one `RuleEvidence` per condition: segment, reason code, field, operator, threshold, actual value, passed, near-threshold, and the policy reference (for example `Customer Segmentation Policy §2.4`). The segmentation engine recorded these when it classified the customer.
3. `CustomerOverviewService` groups the evidence by segment in the priority order from `policies/segmentation.yaml` and turns each condition into a `ConditionCheck` with a plain-English explanation.
4. Each policy reference is resolved by `CustomerOverviewService.quote(ref)`: it splits the reference into document title and section number and looks the section up in an index of the knowledge base. The index is built from the same sanitised chunks the RAG index uses (`chunk_document`), so injected instructions are already removed.
5. Manual-review reasons are mapped to policy sections: data issues and missing evidence to §3, low confidence to §4, no matching rule to §1. Block reasons and strategy references (consent, frequency, loyalty, offers, reminders) are quoted the same way; duplicate references to one section are shown once, keeping the most specific (for example "§2 (stage 2)").
6. The result is a `CustomerOverview` model (`backend/schemas/models.py`), shown by the page and returned by `GET /customers/{id}/overview`.

### 4.4 Where RAG retrieval is still used

| Use | Query sent to the retriever | Consumer |
|---|---|---|
| Email generation guidance | `retrieve_for_strategy`: objective + tone + "tone email guidance", plus reminder stage and dispute terms for REMIND, plus the offer name for offers; filtered to the customer's segment; top 3 | Person 3's writer prompt (soft guidance only) |
| Optional "Ask a question" tab | The question + primary segment + reason codes + block codes + objective, e.g. `Why was this customer classified as LOYAL? LOYAL TENURE_GE_36M ON_TIME_GE_95PCT ACTIVE_LT_30D reward`; top 4, plus up to 3 sections cited by the decision pinned first | `PolicyQAService.answer` (LLM answer with sources, or a deterministic answer) |
| Customer overview | No query: direct section lookup by reference | Policy Chat overview, API |

Off-topic questions in the Ask tab (no domain keyword) skip retrieval and return "Insufficient policy evidence to answer this question."

### 4.5 What the brief asked for, and where it is

| Brief requirement | Implemented in |
|---|---|
| 9 synthetic policy documents, clearly labelled | `knowledge_base/policies/01-09_*.md` (front matter: doc_id, title, version, segments) |
| Policy ingestion | `policy_loader.load_policy_documents` |
| Chunking | `document_processor.chunk_document` (one chunk per `##` section) |
| Treat documents as untrusted | `document_processor.sanitize` removes instruction-like lines and flags the chunk |
| Embeddings | `embedding_service.EmbeddingService` (Sentence Transformers, falls back to TF-IDF) |
| Vector store | `vector_store.ChromaVectorStore` or `LocalVectorStore` (`make_vector_store`) |
| Retrieval with filters | `retriever.PolicyRetriever.retrieve` (segment, document and current-version filters) |
| Policy versioning | `policy_manager.PolicyManager` (sha256 + version per document in the `policies` table) |
| Interpretable segmentation, all matches kept, priority, confidence | `segmentation_engine.SegmentationEngine.classify` with `policies/segmentation.yaml` |
| Select a customer and explain the decision with policy sources | `customer_overview.CustomerOverviewService.overview` (Policy Chat overview tab) |
| Grounded answers; never mix customers | The overview uses only that customer's recorded evidence and exact policy text |
| "Insufficient policy evidence to answer this question." | `policy_qa.INSUFFICIENT` (Ask tab) |
| Policy API | `backend/api/policy_routes.py` |

### 4.6 Files owned

| File | Key functions / classes | Purpose |
|---|---|---|
| `knowledge_base/policies/*.md` | | Loyalty, segmentation, consent, offer eligibility, payment reminder, frequency, tone, privacy, dispute policies |
| `modules/rag/customer_overview.py` | `CustomerOverviewService.overview`, `quote` | The customer overview: category, rule checks with real values, quoted policy proof |
| `modules/segmentation/segmentation_engine.py` | `SegmentationEngine.classify`, `evaluate_condition` | Rule evaluation, reason codes, priority, confidence; records the evidence the overview shows |
| `policies/segmentation.yaml` | | Thresholds, priority, policy references, required fields, confidence settings |
| `modules/rag/policy_loader.py` | `load_policy_documents`, `PolicyDocument` | Reads markdown and front matter |
| `modules/rag/document_processor.py` | `chunk_document`, `sanitize`, `Chunk` | Section chunks, injection stripping (used by both RAG and the overview) |
| `modules/rag/embedding_service.py` | `EmbeddingService` | Neural or TF-IDF vectors |
| `modules/rag/vector_store.py` | `LocalVectorStore`, `ChromaVectorStore` | Stores and searches vectors |
| `modules/rag/retriever.py` | `PolicyRetriever.retrieve`, `retrieve_for_strategy` | Search; tone and wording guidance for Person 3 |
| `modules/rag/policy_qa.py` | `PolicyQAService.answer`, `detect_intents` | Optional free-text Q&A |
| `modules/policy/policy_manager.py` | `PolicyManager` | Version registry |
| `backend/api/policy_routes.py` | | `GET /customers/{id}/overview`, `POST /customers/{id}/policy-query`, `GET /policies` |
| `prompts/policy_qa.txt` | | Prompt for the optional LLM answer |
| `scripts/ingest_policies.py` | | Rebuilds the index |

Models owned in `backend/schemas/models.py`: `SegmentResult`, `RuleEvidence`, `PolicySource`, `PolicyAnswer`, `CustomerOverview`, `SegmentCheck`, `ConditionCheck`, `OverviewReason`, `PolicyQuote`.

UI pages: **Policy Chat** (Customer overview tab, Ask a question tab) and **Customer Classification**.

Tests: `tests/test_customer_overview.py`, `tests/test_segmentation.py`, `tests/test_rag.py`.

### 4.7 Contracts

- **Receives from Person 1:** `CustomerProfile` (with `data_issues`).
- **Gives to Person 3:** `SegmentResult` (status, segments, primary, reason codes, evidence, confidence) and policy guidance excerpts.
- **Reads from Person 3:** the `Strategy` (objective, tone, offer, stage, block reasons, policy references) to show "what happens next" in the overview. It only displays it; it never changes it.
- **Gives to Person 4:** `SegmentResult` and policy version for the audit log; the overview for reviewers.
- **Never:** lets retrieved or quoted text change a segment, offer or block decision; never shows one customer's data in another customer's overview or answer.

### 4.8 Reading order

1. `knowledge_base/policies/02_customer_segmentation_policy.md` and `policies/segmentation.yaml` side by side.
2. `modules/segmentation/segmentation_engine.py` (how `RuleEvidence` is recorded).
3. `modules/rag/customer_overview.py`, then `frontend/pages/4_policy_chat.py`.
4. The overview models at the end of the Person 2 block in `backend/schemas/models.py`.
5. `modules/rag/document_processor.py`, `embedding_service.py`, `vector_store.py`, `retriever.py`.
6. `modules/rag/policy_qa.py` and `prompts/policy_qa.txt` (optional Ask tab).
7. `README.md` sections 10 and 11.
8. `tests/test_customer_overview.py`, `tests/test_segmentation.py`, `tests/test_rag.py`.

### 4.9 Concepts to understand

- **Segment priority:** OVERDUE > DORMANT > DECLINING > LOYAL > CONSISTENT. All matches are kept; the first in priority is the primary segment. The overview shows every segment so the user can see why the others lost.
- **Confidence:** starts at 1.0 and drops by 0.15 when a value is within 10% of a threshold; below 0.6 the customer goes to manual review.
- **Proof by lookup, not by search:** the overview quotes the section the rule itself cites, so the proof is always the exact rule, not the "most similar" text. Similarity search (RAG) is used where exact references do not exist: writer guidance and free-text questions.
- **Why 36% of the Kaggle customers are MANUAL_REVIEW:** about 31% match no rule and about 5% have incomplete usage history. The overview shows this per customer with Customer Segmentation Policy §1 or §3.
- **TF-IDF vs neural embeddings:** TF-IDF matches words, which is why reason codes are added to RAG queries. `EMBEDDING_BACKEND=sentence_transformers` switches to MiniLM.
- **Untrusted documents:** instruction-like lines are removed before indexing, and the overview quotes the same cleaned text.
- **Churn score:** shown for information only; it never decides treatment.

### 4.10 Demo responsibility

Open Policy Chat, select DEMO-A-LOYAL (LOYAL, quoted §2.4, priority over CONSISTENT), DEMO-E-NOCONSENT (blocked, Marketing Consent Policy §3), DEMO-J-MISSING (manual review, §3), and a real Kaggle customer such as CUST0000000002 (DORMANT).

### 4.11 Likely judge questions

- Why does the overview not use the LLM? What does RAG still do?
- Why is a rule engine used for segmentation instead of the LLM or the churn model?
- How do you know the quoted text is the rule that was actually applied?
- How do you stop a poisoned policy document from instructing the model?
- How do you guarantee one customer's data never appears in another customer's overview?
- What changes if a policy threshold changes?

## 5. Person 3: Offers, strategy selection and LLM email generation

### 5.1 Mission

Decide what to say and with which approved offer (in Python), then have the LLM write it as structured JSON, repairing or falling back to an approved template when it fails validation.

### 5.2 What the brief asked for, and where it is

| Brief requirement | Implemented in |
|---|---|
| Approved, configurable offer catalog | `policies/offers.yaml`, `offer_catalog.load_catalog`, `OfferRepository` |
| Python offer eligibility | `offer_eligibility.check_offer`, `evaluate_catalog`, `select_offer` |
| Strategy mapping (objective, tone, offer, template) | `policies/communication.yaml` `strategy_map`, `StrategySelector.select` |
| Reminder stages 1-15 / 16-30 / 31+ days | `policies/payment_reminders.yaml`, `reminder_stage_for` |
| Suppression: NO_CONSENT, RECENT_CONTACT, no promos when overdue, escalate bad data | `StrategySelector.select` (block reasons with policy references) |
| Verified facts for the LLM | `StrategySelector.build_facts` (`Strategy.facts`) |
| Structured JSON email (subject, body, CTA, facts_used) | `email_generator.EmailGenerator.generate`, `EmailContent` model |
| Prompt engineering and versioning | `prompts/email_generation.txt`, `email_repair.txt`, `prompt_manager.PromptManager` |
| Claude, compatible provider, static fallback | `llm_client.AnthropicProvider`, `OpenAICompatibleProvider`, `NoLLMProvider` |
| Targeted repair, format retry, static fallback | `generation_service.GenerationService.generate` |
| Static templates | `knowledge_base/templates/TPL_*.txt` |
| Offline testing and fault injection (scenario G) | `simulators.OfflineSimulatorProvider`, `FaultInjectingProvider` |
| Generation API | `backend/api/generation_routes.py` |

### 5.3 Files owned

| File | Key functions / classes | Purpose |
|---|---|---|
| `policies/offers.yaml` | | 6 offers incl. `LOYALTY_001`, `REENGAGE_001`, `WINBACK_001`, `THANKS_001`; `LOYALTY_2025` is deliberately expired (scenario F) |
| `policies/communication.yaml` | | Strategy map, cooldowns (7 days marketing, 5 days reminders), support contacts, wording rules |
| `policies/payment_reminders.yaml` | | Stages, tones, templates, must-include facts |
| `modules/offers/*` | `load_catalog`, `OfferRepository`, `check_offer`, `select_offer` | Catalog and eligibility (segment, tenure, dates, channel, status) |
| `modules/strategy/strategy_selector.py` | `StrategySelector.select`, `build_facts`, `reminder_stage_for` | Objective, tone, template, offer, stage, blocks, facts |
| `modules/generation/llm_client.py` | `get_provider`, `extract_json`, providers | Provider abstraction; robust JSON parsing |
| `modules/generation/prompt_manager.py` | `PromptManager.render`, `version` | Versioned prompts |
| `modules/generation/email_generator.py` | `EmailGenerator.generate`, `repair`, `TemplateStore`, `render_placeholders` | Calls the LLM, fills placeholders from verified facts |
| `modules/generation/generation_service.py` | `GenerationService.generate`, `static_draft` | Attempt loop: LLM, repair (max 2), format retry, static fallback |
| `modules/generation/simulators.py` | `OfflineSimulatorProvider`, `FaultInjectingProvider` | Labelled fake LLM for tests and demos |
| `prompts/email_generation.txt`, `prompts/email_repair.txt` | | Writer and repair prompts |
| `knowledge_base/templates/TPL_*.txt` | | 7 approved templates (THANKS, LOYALTY, REENGAGE, REACTIVATE, REMIND_S1-S3) |
| `backend/api/generation_routes.py` | | `GET /offers`, `POST /customers/{id}/strategy`, `POST /customers/{id}/draft` |

UI pages: **Offer and Strategy**, **Email Generator**.

Tests: `tests/test_offers.py`, `tests/test_strategy.py`, `tests/test_generation.py`.

### 5.4 Contracts

- **Receives:** `CustomerProfile` (Person 1), `SegmentResult` and policy guidance (Person 2).
- **Gives to Person 4:** `Strategy` (with `facts`, `offer`, `block_reasons`, `policy_refs`) and `EmailContent`; the list of generation attempts.
- **Uses from Person 4:** the validator, injected as a function. Generation cannot skip it.
- **Never:** invents an offer, amount, date or plan; puts a promotion in a reminder; lets the LLM choose the offer.

### 5.5 Reading order

1. `policies/communication.yaml`, `offers.yaml`, `payment_reminders.yaml`.
2. `modules/strategy/strategy_selector.py`.
3. `modules/offers/offer_eligibility.py`.
4. `prompts/email_generation.txt` and `email_repair.txt`.
5. `modules/generation/email_generator.py`, then `generation_service.py`, then `llm_client.py`.
6. `knowledge_base/templates/`.
7. `README.md` sections 12, 13, 14 and 16.
8. `tests/test_strategy.py`, `tests/test_generation.py`.

### 5.6 Concepts to understand

- **Placeholders, not numbers:** the LLM writes `{amount_due}`; code renders the verified value. This is why amounts cannot be hallucinated into the final text, and why the validator still checks every number.
- **Failure categories decide the next step:** DATA and POLICY failures block (no LLM retry); WRITING failures get a targeted repair prompt; FORMAT failures get one retry. Maximum 2 repairs, then the static template, then BLOCKED.
- **Suppression is separate from segmentation:** a LOYAL customer without consent is still LOYAL, but marketing is blocked.
- **Fallback strategy:** if a REQUIRED offer is unavailable (for example expired), LOYAL falls back to APPRECIATION / TPL_THANKS.
- **Low temperature and structured JSON:** reduces variation; `extract_json` tolerates code fences.
- **Provider switch:** `.env` decides: Claude if `ANTHROPIC_API_KEY` is set, else the OpenAI-compatible endpoint (currently local `gemma3:4b`), else templates only.

### 5.7 Demo responsibility

Scenarios **A** (loyal, reward), **B** (declining, re-engagement), **C** (dormant, win-back) and **F** (expired offer: recomputed, never shown).

### 5.8 Likely judge questions

- How do you stop the LLM from inventing a discount?
- What happens when the LLM returns broken JSON?
- Why not just regenerate until the email passes?
- How does the system behave with no API key at all?
- What does it cost per email, and how many LLM calls does a draft take at most?

## 6. Person 4: Validation, review, mock email, audit, UI, API and evaluation

### 6.1 Mission

Guarantee safety: no draft reaches a customer (even a mock one) unless deterministic checks pass and a human approves. Person 4 also owns the integration layer, the Streamlit and FastAPI apps, observability and the evaluation harness.

### 6.2 What the brief asked for, and where it is

| Brief requirement | Implemented in |
|---|---|
| Deterministic validation engine (16 required checks) | `validation/validator.EmailValidator` with 27 named checks |
| Amount, date, percentage, unsupported numbers | `fact_validator.py` |
| Offer existence, eligibility, expiry, terms | `offer_validator.py` |
| Payment consistency, overdue stage | `payment_validator.py` |
| Consent, frequency, duplicate outreach | `consent_validator.py` (+ contact history) |
| PII leakage (regex, optional Presidio) | `pii_validator.py` |
| Tone rules + advisory LLM tone judge (1-5 scores) | `tone_validator.run`, `judge`; `prompts/tone_judge.txt` |
| Failure categories DATA / POLICY / WRITING / FORMAT | `FailureCategory` in `models.py`; each finding carries one |
| Human review: approve, edit (revalidate), reject, regenerate with feedback | `review/review_service.ReviewService` |
| Failed validation disables approval | `ReviewService.can_approve` |
| Mock email with pre-send gate, at most once per draft | `email/mock_email_service.MockEmailService` (`UNIQUE(draft_id)`) |
| Audit store with redaction | `audit/audit_service.AuditService`, `redact` |
| Observability metrics | `audit/metrics.compute_metrics` |
| Evaluation of scenarios and planted errors | `evaluation/evaluation.run_evaluation`; `reports/evaluation_report.md` |
| SQLite schema (12 tables) and transactions | `backend/database/db.py` |
| Integration and wiring | `backend/services/*` |
| Streamlit app (9 pages) and FastAPI app | `app.py`, `frontend/*`, `main.py`, `backend/api/review_routes.py` |

### 6.3 Files owned

| File | Key functions / classes | Purpose |
|---|---|---|
| `modules/validation/validator.py` | `EmailValidator.validate`, `failure_messages` | Runs every check, orders findings, decides pass/fail |
| `modules/validation/context.py` | `ValidationContext`, `finding` | Shared input for all checks |
| `modules/validation/fact_validator.py` | `check_amounts`, `check_dates`, `check_percentages`, `check_unsupported_numbers`, `check_placeholders` | Groundedness |
| `modules/validation/offer_validator.py`, `payment_validator.py`, `consent_validator.py`, `pii_validator.py`, `tone_validator.py` | `run` | One area each |
| `modules/review/review_service.py` | `queue`, `can_approve`, `approve`, `edit`, `reject`, `regenerate` | Reviewer workflow |
| `modules/review/draft_repository.py` | `DraftRepository` | Drafts, attempts, validations, reviews, contact history |
| `modules/email/mock_email_service.py` | `pre_send_checks`, `send`, `outbox` | Mock delivery with the final gate |
| `modules/audit/audit_service.py`, `metrics.py` | `AuditService.log`, `trace`, `compute_metrics` | Audit trail and dashboard metrics |
| `modules/evaluation/evaluation.py` | `run_evaluation`, `to_markdown` | Isolated evaluation run and report |
| `backend/database/db.py` | `Database` | Schema, transactions, queries |
| `backend/services/container.py`, `engagement_service.py`, `bootstrap.py`, `formatting.py` | | Wiring, main pipeline, data setup helpers |
| `backend/api/review_routes.py`, `deps.py`, `main.py` | | `/drafts/{id}/validate`, `/review/*`, `/send/{id}`, `/audit/{id}`, `/metrics`, `/health` |
| `app.py`, `frontend/pages/*`, `frontend/utils/ui.py` | | Streamlit UI (all 9 pages; content of pages 2-6 showcases P1-P3) |
| `policies/privacy.yaml` | | Protected fields, redaction keys, PII patterns |
| `scripts/run_evaluation.py`, `demo_e2e.py`, `setup_all.py` | | Evaluation, terminal demo, one-command setup |

UI pages: **Human Review**, **Audit and Observability**, **Evaluation**, **Executive Dashboard** KPIs, plus the shared UI framework.

Tests: `tests/test_validation.py`, `test_review.py`, `test_mock_email.py`, `test_api.py`, `test_frontend_smoke.py`, `test_integration.py`.

### 6.4 Draft lifecycle (must be able to draw it)

`PENDING_REVIEW` -> `APPROVED` -> `MOCK_SENT`. Side states: `NEEDS_FIX` (an edit failed validation), `BLOCKED` (data/policy failure, or still failing after fallback), `REJECTED`, `CANCELLED` (superseded). There is no edge into `MOCK_SENT` except from `APPROVED` through `pre_send_checks`.

### 6.5 Contracts

- **Receives:** `Strategy` and `EmailContent` (Person 3), `SegmentResult` (Person 2), `CustomerProfile` (Person 1).
- **Gives to Person 3:** `ValidationReport` with categorised findings, so generation knows whether to repair, retry or stop.
- **Gives to everyone:** the audit trail and metrics.
- **Never:** lets the tone judge approve anything (advisory only); sends without approval; logs names or emails.

### 6.6 Reading order

1. `modules/validation/validator.py` (`CHECK_ORDER` lists all 27 checks).
2. `fact_validator.py`, then the other validators.
3. `modules/review/review_service.py` and `modules/email/mock_email_service.py`.
4. `backend/services/engagement_service.py` and `container.py`.
5. `backend/database/db.py` (tables).
6. `modules/audit/*`, `modules/evaluation/evaluation.py`, `reports/evaluation_report.md`.
7. `README.md` sections 15, 16, 17, 18, 19 and 24-25.
8. `tests/test_validation.py`, `test_review.py`, `test_mock_email.py`, `test_integration.py`.

### 6.7 Concepts to understand

- **Deterministic vs advisory checks:** amounts, dates, offers, consent and payment are checked by code. The LLM tone judge only adds warnings.
- **Revalidation on edit:** every human edit runs the full validator again; a failing edit becomes `NEEDS_FIX` and cannot be approved.
- **Pre-send gate:** re-checks validation, consent, frequency, approval and "not already sent" at send time, because state may have changed since approval.
- **Idempotency:** creating a draft returns the open one unless `supersede=true`; delivery is unique per draft.
- **Evaluation numbers:** classification accuracy, validator catch rate on planted errors, false positives on approved templates, first-pass rate, groundedness, offer and consent compliance.

### 6.8 Demo responsibility

Scenarios **D** (overdue stages 1-3, no offer, dispute link), **E** (no consent blocked), **G** (hallucinated amount caught, repaired or fallback), then the review, approve, mock send and audit trail walkthrough.

### 6.9 Likely judge questions

- Show that a failed draft cannot be approved or sent.
- Why are validators deterministic instead of asking the LLM to check itself?
- What exactly is in the audit log for one draft, and what is redacted?
- How do you prevent sending the same email twice?
- What does a 53% first-pass rate in the evaluation mean? (It includes deliberately injected faults.)

## 7. Hand-offs between people

| From | To | Contract (in `models.py`) | Created by | Consumed by |
|---|---|---|---|---|
| P1 | P2, P3, P4 | `CustomerProfile` (+ `DataIssue`) | `build_profile` | `SegmentationEngine.classify`, `StrategySelector`, validators |
| P2 | P3, P4 | `SegmentResult` (+ `RuleEvidence`) | `SegmentationEngine.classify` | `StrategySelector.select`, audit |
| P2 | P3 | `PolicySource` excerpts | `retrieve_for_strategy` | `EmailGenerator` prompt |
| P2 | P4 (UI, API) | `CustomerOverview` (+ `SegmentCheck`, `ConditionCheck`, `PolicyQuote`) | `CustomerOverviewService.overview` | Policy Chat page, `GET /customers/{id}/overview` |
| P3 | P4 | `Strategy` (+ `Offer`, `BlockReason`, facts) | `StrategySelector.select` | validators, review UI, audit |
| P3 | P4 | `EmailContent` | `EmailGenerator.generate` | `EmailValidator.validate` |
| P4 | P3 | `ValidationReport` (+ `FailureCategory`) | `EmailValidator.validate` | `GenerationService` repair loop |
| P4 | all | `Draft`, audit events, metrics | `EngagementService`, `AuditService` | UI, API, evaluation |

Integration rules: a contract change needs an update to `API_CONTRACTS.md` and agreement from every consumer; `tests/test_integration.py` and `tests/test_api.py` must pass before merging.

## 8. Built versus the brief

### 8.1 Done

All 13 build phases, all 9 Streamlit pages, all 18 required API endpoints (plus `/customers/{id}/overview` and `/policies`), scenarios A-H (plus extra demo customers for reminder stages 1 and 3, recent contact, missing data and a consistent customer), the 16 required validation checks (27 named checks in total), human review with revalidation, mock email, audit, metrics, evaluation report, all four team documents, `CLAUDE.md`, `architecture.mmd`, `demo_scenarios.md`.

### 8.2 Deliberate deviations

| Brief | Built | Reason |
|---|---|---|
| SQLAlchemy | Standard-library `sqlite3` with transactions | Fewer dependencies; documented in `README.md` §6 |
| ChromaDB + Sentence Transformers | Supported; this machine currently runs the TF-IDF + local store fallback | Works offline without downloading the embedding model |
| Anthropic Claude | Supported; currently a local `gemma3:4b` via Ollama until an API key is added | No paid key yet; switch by setting `ANTHROPIC_API_KEY` in `.env` |
| `backend/models/` folder | Models live in `backend/schemas/models.py` | One shared contract file |
| Policy chat: select a customer, then type a question | Policy Chat opens on a Customer overview: selecting a customer immediately shows the category, every rule check and the quoted policy proof. Free-text questions remain as an optional second tab. | Requested by the team: explain a customer without having to ask |

### 8.3 Open gaps (to do before submission)

- **No Dockerfile or docker-compose.yml.** The brief asks for Docker; the team chose to leave it out (`README.md` §23 lists the three steps a container needs). Person 4 owns this if it is added back.
- Neural embeddings are not active on this machine (Person 2): set `EMBEDDING_BACKEND=sentence_transformers` once the MiniLM model is downloaded.
- About 36% of the Kaggle customers land in MANUAL_REVIEW because they match no segment rule (Person 2 and Person 3 to decide whether the policy needs a default segment).
- The evaluation report was produced with the offline simulator; re-run it with the real LLM before the final demo.

## 9. Glossary

| Term | Meaning |
|---|---|
| Segment | Rule-based customer category (OVERDUE, DORMANT, DECLINING, LOYAL, CONSISTENT) |
| Primary segment | The first matching segment in the priority order |
| Reason code | Short code for one rule that matched, e.g. `TENURE_GE_36M` |
| Strategy | Objective, tone, template, offer, stage and blocks for one customer |
| Suppression / block | A policy reason that stops outreach (NO_CONSENT, RECENT_CONTACT, MANUAL_REVIEW) |
| Facts | Verified values (amount, dates, contacts) that fill template placeholders |
| RAG | Retrieval-augmented generation: find relevant policy text and give it to the model |
| Chunk | One section of a policy document, indexed for search |
| Repair | A targeted prompt asking the LLM to fix only the failed parts |
| Static fallback | An approved template filled with verified facts, used when the LLM keeps failing |
| Pre-send gate | Final checks run at the moment of mock delivery |
| Provenance | Whether a field is ORIGINAL (Kaggle) or SYNTHETIC |
