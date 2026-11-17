# Integration guide

## How the modules connect

```
EngagementService.create_draft(customer_id)                       backend/services/engagement_service.py
 ├─ CustomerRepository.get_row → build_profile (P1)                data gate runs here
 ├─ SegmentationEngine.classify (P2)                               MANUAL_REVIEW on bad data
 ├─ StrategySelector.select (P3)                                   suppression + offer eligibility + facts
 │    └─ blocked? → Draft BLOCKED, audit DRAFT_BLOCKED, return     (LLM never called)
 ├─ PolicyRetriever.retrieve_for_strategy (P2)                     soft tone/wording guidance only
 ├─ GenerationService.generate(strategy, provider, validate_fn)    (P3) repair / format retry / static fallback
 │    └─ validate_fn = EmailValidator.validate (P4)                 injected, cannot be skipped
 ├─ tone judge (P4, advisory, only on passing drafts)
 └─ DraftRepository.insert + attempts + validation report, AuditService.log (P4)
ReviewService (P4) → approve / edit (re-validate) / reject / regenerate
MockEmailService.send (P4) → pre-send gate (re-validate with fresh data) → mock_deliveries + contact_history + audit
```

`backend/services/container.py` builds every service exactly once. Streamlit (`frontend/utils/ui.get_c`) and FastAPI (`backend/api/deps.container`) both use it.

## Working independently

- **P1** can work with only the profile tests: `pytest tests/test_data.py tests/test_profiles.py`.
- **P2** can rebuild the index with `python scripts/ingest_policies.py`, then run `pytest tests/test_rag.py tests/test_segmentation.py`.
- **P3** can develop prompts offline with `LLM_PROVIDER=offline_simulator`. Fault injection (`inject_fault`) exercises the repair loop without an API key.
- **P4** can run `pytest tests/test_validation.py` against the approved templates; every template must pass.

## Integration rules

1. **Decisions belong to P2 and P3, in YAML.** Writing (P3 prompts) must never decide eligibility, offers or stages.
2. **Every path to the customer goes through `EmailValidator.validate`**, including edits and the pre-send gate.
3. **New facts:** a fact the writer needs must be (a) produced by `StrategySelector.build_facts`, (b) on the `llm_context_allowed_fields` list, and (c) checked by the validator if it contains numbers or dates.
4. **New offers:** add them to `offers.yaml` only. Eligibility, validation and the UI pick them up automatically.
5. **New segments:**
   1. Add the rule to `segmentation.yaml` and its priority.
   2. Add a strategy to `communication.yaml`.
   3. Add a template to `knowledge_base/templates/`.
   4. Add a policy section.
   5. Add a labelled demo customer.
6. **Schema changes:** edit `backend/schemas/models.py`, update `API_CONTRACTS.md`, and run the full suite.

## End-to-end checks

```bash
python -m pytest -q                       # 119 passed, 1 skipped (TestClient test skipped without FastAPI)
python scripts/run_evaluation.py          # scenarios, planted errors, injected faults
python scripts/demo_e2e.py --send         # prints every scenario and mock-sends passing drafts
```
