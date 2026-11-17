# Dataset profiling report

- File: `data/raw/customer_churn_1m.csv`
- Rows profiled: **1,000,000**
- Columns: **32**
- Duplicate customer IDs: **0**

## Columns

| Column | dtype | Nulls | Null % | Mapping |
|---|---|---|---|---|
| customer_id | str | 0 | 0.00% | customer_id |
| signup_date | str | 0 | 0.00% | DROPPED (protected/unused) |
| age | int64 | 0 | 0.00% | DROPPED (protected/unused) |
| gender | str | 0 | 0.00% | DROPPED (protected/unused) |
| annual_income | float64 | 29,959 | 3.00% | DROPPED (protected/unused) |
| education | str | 0 | 0.00% | DROPPED (protected/unused) |
| marital_status | str | 0 | 0.00% | DROPPED (protected/unused) |
| dependents | int64 | 0 | 0.00% | DROPPED (protected/unused) |
| tenure | int64 | 0 | 0.00% | tenure_months |
| contract | str | 0 | 0.00% | contract_type |
| payment_method | str | 0 | 0.00% | payment_method |
| paperless_billing | str | 0 | 0.00% | paperless_billing |
| senior_citizen | int64 | 0 | 0.00% | DROPPED (protected/unused) |
| monthlycharges | float64 | 0 | 0.00% | monthly_charges |
| totalcharges | float64 | 0 | 0.00% | total_charges |
| num_services | int64 | 0 | 0.00% | num_services |
| has_phone_service | int64 | 0 | 0.00% | unmapped |
| has_internet_service | int64 | 0 | 0.00% | unmapped |
| has_online_security | int64 | 0 | 0.00% | unmapped |
| has_online_backup | int64 | 0 | 0.00% | unmapped |
| has_device_protection | int64 | 0 | 0.00% | unmapped |
| has_tech_support | int64 | 0 | 0.00% | unmapped |
| has_streaming_tv | int64 | 0 | 0.00% | unmapped |
| has_streaming_movies | int64 | 0 | 0.00% | unmapped |
| customer_satisfaction | float64 | 19,921 | 1.99% | customer_satisfaction |
| num_complaints | float64 | 29,906 | 2.99% | num_complaints |
| num_service_calls | int64 | 0 | 0.00% | customer_service_calls |
| late_payments | int64 | 0 | 0.00% | late_payments |
| avg_monthly_gb | float64 | 50,012 | 5.00% | avg_monthly_gb |
| days_since_last_interaction | int64 | 0 | 0.00% | days_since_last_interaction |
| credit_score | float64 | 40,395 | 4.04% | DROPPED (protected/unused) |
| churn | int64 | 0 | 0.00% | churn_status |

## Numeric columns

| Column | Min | Max | Mean |
|---|---|---|---|
| age | 18.0 | 90.0 | 44.7246 |
| annual_income | 20000.0 | 250000.0 | 58788.3119 |
| dependents | 0.0 | 5.0 | 0.7998 |
| tenure | 1.0 | 72.0 | 22.3819 |
| senior_citizen | 0.0 | 1.0 | 0.1995 |
| monthlycharges | 20.0 | 854.9567301092312 | 86.4437 |
| totalcharges | 16.3 | 16252.86150782197 | 1837.3214 |
| num_services | 1.0 | 6.0 | 2.5637 |
| has_phone_service | 0.0 | 1.0 | 0.7696 |
| has_internet_service | 0.0 | 1.0 | 0.8497 |
| has_online_security | 0.0 | 1.0 | 0.3395 |
| has_online_backup | 0.0 | 1.0 | 0.4257 |
| has_device_protection | 0.0 | 1.0 | 0.2971 |
| has_tech_support | 0.0 | 1.0 | 0.4973 |
| has_streaming_tv | 0.0 | 1.0 | 0.6 |
| has_streaming_movies | 0.0 | 1.0 | 0.5491 |
| customer_satisfaction | 1.0 | 9.0 | 6.1591 |
| num_complaints | 0.0 | 7.0 | 0.7017 |
| num_service_calls | 0.0 | 12.0 | 1.7602 |
| late_payments | 0.0 | 5.0 | 0.401 |
| avg_monthly_gb | 0.0 | 557.8240230551536 | 39.0952 |
| days_since_last_interaction | 1.0 | 365.0 | 44.4942 |
| credit_score | 300.0 | 850.0 | 678.5621 |
| churn | 0.0 | 1.0 | 0.0992 |

## Categorical values (top values)

