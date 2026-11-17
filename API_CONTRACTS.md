# API and module contracts

## Module contracts (Python)

| Producer | Function | Input | Output |
|---|---|---|---|
| P1 | `profile_builder.build_profile(row, settings)` | customers table row (dict) | `CustomerProfile`, including `data_issues` and `field_sources` |
| P1 | `CustomerRepository.search(query, segment, source, limit, offset)` | filters | list of summary dicts |
| P2 | `SegmentationEngine.classify(profile)` | `CustomerProfile` | `SegmentResult`: status `CLASSIFIED` or `MANUAL_REVIEW`, segments, primary, reason codes, evidence, confidence |
| P2 | `PolicyRetriever.retrieve(query, top_k, segments, doc_ids, min_score)` | text + filters | list of `PolicySource` |
| P2 | `PolicyQAService.answer(customer_id, question)` | id + question | `PolicyAnswer` (answer, sources, insufficient_evidence, mode) |
| P3 | `StrategySelector.select(profile, segment, history, forced_offer_id)` | profile, segment, contact history | `Strategy`: objective, tone, template, stage, offer, offer decisions, blocked, block reasons, facts |
| P3 | `GenerationService.generate(strategy, provider, validate_fn, guidance, feedback)` | strategy + an injected validator | `GenerationOutcome` (content, report, attempts, mode) |
| P4 | `EmailValidator.validate(content, strategy, profile, segment, history)` | draft + context | `ValidationReport` |
| P4 | `ReviewService.approve/edit/reject/regenerate` | draft id + reviewer | `Draft` (raises `ReviewError`) |
| P4 | `MockEmailService.send(draft_id)` | draft id | delivery dict (raises `DeliveryError`) |
| Integration | `EngagementService.create_draft(customer_id, forced_offer_id, fault, feedback, supersede)` | id + options | `Draft` |

## Key schemas

```text
CustomerProfile { customer_id, customer_name, email_address, tenure_months, contract_type, monthly_charges, total_charges,
  usage_last_3m, usage_prev_3m, last_active_date, bill_due_date, amount_due, payment_status (PAID|UNPAID|PARTIAL),
  on_time_payment_ratio, marketing_consent, last_contacted_date, churn_status, customer_service_calls, ...,
  as_of_date, days_since_active, days_overdue, days_since_contact, data_issues[DataIssue], field_sources{field: original|derived|synthetic} }

SegmentResult { customer_id, status, segments[], primary_segment, secondary_segments[], reason_codes[],
  evidence[RuleEvidence{segment, reason_code, field, operator, threshold, actual, passed, near_threshold, policy_ref}],
  confidence, manual_review_reasons[], churn_status_info, policy_version }

Strategy { customer_id, primary_segment, objective, tone, template_id, reminder_stage, is_marketing, offer: Offer|null,
  offer_decisions[{offer_id, eligible, reasons[]}], blocked, block_reasons[{code, category, detail, policy_ref}],
  notes[], facts{allow-listed verified facts}, policy_refs[], policy_version }

EmailContent { subject (3-120), body (20-4000), cta }

ValidationReport { passed, findings[{check, status PASS|FAIL|WARN, severity BLOCK|WARN|INFO, category DATA|POLICY|WRITING|FORMAT, detail}],
  retry_recommended, failure_categories[], tone_scores }

Draft { draft_id, customer_id, status, subject, body, cta, objective, tone, template_id, offer_id, reminder_stage,
  facts_used, strategy, segment, prompt_version, model_name, policy_version, generation_mode, attempt_count, block_reasons[] }
```

## REST endpoints

| Method and path | Request | Success | Errors |
|---|---|---|---|
| `GET /health` | | `{status, customers, llm, rag, policy_version, as_of_date}` | |
| `GET /customers?q&segment&source&limit&offset` | query parameters | `{total, limit, offset, items[]}` | 422 |
| `GET /customers/{id}` | | `CustomerProfile` JSON | 404 |
| `POST /customers/upload?limit` | multipart `file` (.csv) | `{loaded, missing_mapped_columns, cleaning, source}` | 422 (not a CSV, or the mapping fails) |
| `POST /customers/{id}/classify` | | `SegmentResult` | 404 |
| `POST /customers/{id}/policy-query` | `{question, top_k}` | `PolicyAnswer` (without decision_evidence) | 404, 422 |
| `GET /policies` | | `{documents[], rule_files{}, index{}}` | |
| `GET /offers` | | `{catalog_version, global_rules, offers[]}` | |
| `POST /customers/{id}/strategy` | `{forced_offer_id?}` | `{segment, strategy}` | 404 |
| `POST /customers/{id}/draft` | `{forced_offer_id?, inject_fault?, supersede?, requested_by?}` | 201 `{draft, validation, attempts}` | 404, 422 |
| `POST /drafts/{id}/validate` | | `ValidationReport` (re-run with fresh data) | 404, 409 |
| `GET /review/queue?status&limit` | | list of draft summaries | 422 |
| `POST /review/{id}/approve` | `{reviewer}` | `Draft` | 404, 409 |
| `POST /review/{id}/edit` | `{reviewer, subject, body, cta?}` | `{draft, validation}` | 404, 409 |
| `POST /review/{id}/reject` | `{reviewer, reason}` | `Draft` | 404, 409 |
| `POST /review/{id}/regenerate` | `{reviewer, feedback}` | 201 new `Draft` | 404, 409 |
| `POST /send/{id}` | `{reviewer}` | `{draft_id, message_id, status: MOCK_SENT, to (masked)}` | 404, 409 (not approved, already delivered, pre-send failure, already paid) |
| `GET /audit/{id}` | | `{record, draft, attempts, validations, reviews, delivery, events}` | 404 |
| `GET /metrics` | | metrics dict | |
