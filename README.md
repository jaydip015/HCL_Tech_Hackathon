# Person 3: Offer catalog, strategy selection and LLM email generation

> These are **copies** for reading and study. The application still runs from the original files in the
> project root; editing a file here changes nothing in the running app. Make real changes in the
> original location (same relative path) and run `python -m pytest -q` from the project root.

## What this person owns

Choose the objective, tone, template, reminder stage and approved offer in Python (with suppression for no consent, recent contact, overdue and bad data), then have the LLM write structured JSON using placeholders for verified facts, with targeted repair and a static-template fallback.

- **Hands off:** Strategy (+ Offer, BlockReason, facts) and EmailContent to Person 4
- **Demo:** Scenarios A (loyal), B (declining), C (dormant) and F (expired offer recomputed)
- **Full guide:** `../shared/TEAM_HANDBOOK.md` (section 5: reading order, concepts, judge questions)

## UI pages that show this work

- `frontend/pages/5_offer_strategy.py`
- `frontend/pages/6_email_generator.py`

The UI pages are owned and maintained by Person 4; they call this person's modules.

## Shared files this person must also read (in `../shared/`)

- `backend/schemas/models.py`: the contracts passed between all four people
- `config.py`, `CLAUDE.md`, `README.md`, `TEAM_HANDBOOK.md`, `API_CONTRACTS.md`, `INTEGRATION_GUIDE.md`
- `tests/conftest.py`, `tests/fakes.py`: test fixtures used by this person's tests

## Files in this folder (28)

**backend/** - API routes, services, database

- `backend/api/generation_routes.py`

**knowledge_base/** - Policy documents / approved templates

- `knowledge_base/templates/TPL_LOYALTY.txt`
- `knowledge_base/templates/TPL_REACTIVATE.txt`
- `knowledge_base/templates/TPL_REENGAGE.txt`
- `knowledge_base/templates/TPL_REMIND_S1.txt`
- `knowledge_base/templates/TPL_REMIND_S2.txt`
- `knowledge_base/templates/TPL_REMIND_S3.txt`
- `knowledge_base/templates/TPL_THANKS.txt`

**modules/** - Business logic

- `modules/generation/__init__.py`
- `modules/generation/email_generator.py`
- `modules/generation/generation_service.py`
- `modules/generation/llm_client.py`
- `modules/generation/prompt_manager.py`
- `modules/generation/simulators.py`
- `modules/offers/__init__.py`
- `modules/offers/offer_catalog.py`
- `modules/offers/offer_eligibility.py`
- `modules/offers/offer_repository.py`
- `modules/strategy/__init__.py`
- `modules/strategy/strategy_selector.py`

**policies/** - Business rules (YAML)

- `policies/communication.yaml`
- `policies/offers.yaml`
- `policies/payment_reminders.yaml`

**prompts/** - Versioned LLM prompts

- `prompts/email_generation.txt`
- `prompts/email_repair.txt`

**tests/** - Automated tests

- `tests/test_generation.py`
- `tests/test_offers.py`
- `tests/test_strategy.py`
