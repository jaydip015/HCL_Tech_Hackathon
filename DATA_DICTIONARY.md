# Data dictionary

Provenance values:

- **ORIGINAL:** taken from the Kaggle file.
- **DERIVED:** computed from original columns.
- **SYNTHETIC:** generated deterministically from `hash(seed, customer_id, field)`.

Demo customers (`data_source='demo'`) are entirely synthetic and hand-labelled.

## Kaggle source columns (32) and how each one is used

| Source column | Internal field | Use |
|---|---|---|
| customer_id | customer_id | Primary key |
| tenure | tenure_months | LOYAL rule, offer minimum tenure |
| contract | contract_type | Display; a verified fact for emails |
| payment_method | payment_method | Display |
| paperless_billing | paperless_billing | Display |
| monthlycharges | monthly_charges | Synthetic amount due; display |
| totalcharges | total_charges | Display. Missing values are imputed as monthly × tenure (documented). |
| num_services | num_services | Display |
| customer_satisfaction | customer_satisfaction | Display |
| num_complaints | num_complaints | Display |
| num_service_calls | customer_service_calls | Display |
| late_payments | late_payments | Derives the on-time ratio; drives the unpaid probability |
| avg_monthly_gb | avg_monthly_gb | Derives usage_prev_3m |
| days_since_last_interaction | days_since_last_interaction | Derives last_active_date |
| churn | churn_status | **Display only.** Influences the synthetic usage trend; never drives treatment. |
| has_* (8 service flags) | (ignored) | Not needed |
| gender, age, senior_citizen, marital_status, dependents, education, annual_income, credit_score | **dropped** | Protected attributes or proxies; never stored |
| signup_date | dropped | Tenure is used instead |

## customers table: engagement fields

| Field | Type | Provenance | Rule |
|---|---|---|---|
| customer_name | text | SYNTHETIC | From fixed name lists |
| email_address | text | SYNTHETIC | `first.last###@example.com` (reserved domain) |
| last_active_date | date | DERIVED | as_of − days_since_last_interaction |
| usage_prev_3m | GB | DERIVED | avg_monthly_gb × 3 ± 10% |
| usage_last_3m | GB | SYNTHETIC | 85–115% of usage_prev_3m. Churned customers decline with 60% probability. Customers inactive 90+ days fall below 20%. |
| on_time_payment_ratio | 0–1 | DERIVED | 1 − late_payments / min(max(tenure, 1), 36) |
| payment_status | PAID / UNPAID / PARTIAL | SYNTHETIC | P(unpaid) = 0.03 + 0.06 × late_payments (max 0.6). 20% of unpaid bills are PARTIAL. |
| bill_due_date | date | SYNTHETIC | PAID: a future date. Unpaid: 30% not yet due, otherwise 1 to (10 + 15 × late) days past due (max 120). |
| amount_due | currency | SYNTHETIC | PAID: 0. UNPAID: monthly × months outstanding. PARTIAL: 30–70% of monthly. |
| marketing_consent | 0/1 | SYNTHETIC | 85% consented |
| last_contacted_date | date | SYNTHETIC | 60% were contacted 1–120 days ago |
| customer_support_contact | text | SYNTHETIC | Support phone from communication.yaml |
| contact_frequency | text | SYNTHETIC | Preference only (MONTHLY / QUARTERLY / WEEKLY); display only |
| data_source | text | | kaggle / sample / demo |

## Derived at profile build time (not stored)

| Field | Rule |
|---|---|
| days_since_active | as_of − last_active_date |
| days_overdue | as_of − bill_due_date, when the status is UNPAID or PARTIAL, the amount is above 0 and the due date has passed; otherwise 0 |
| days_since_contact | as_of − last_contacted_date |
| data_issues | Data-quality gate. BLOCK codes: CONTRADICTORY_PAYMENT, MISSING_AMOUNT, MISSING_DUE_DATE, INVALID_PAYMENT_STATUS, MISSING_TENURE, MISSING_ACTIVITY, MISSING_USAGE, INVALID_*. WARN codes: UNVERIFIED_CONSENT, FUTURE_CONTACT. |

## Verified facts allowed in LLM prompts (`policies/privacy.yaml`)

first_name, tenure_months, tenure_years, contract_type, amount_due, due_date, days_overdue, reminder_stage, offer_id, offer_name, offer_value, offer_description, offer_terms, offer_expiry, support_phone, support_email, dispute_url, company_name.
