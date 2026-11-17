# Evaluation report - Customer Loyalty and Engagement Assistant

- Generated: 2026-11-17T09:01:03.691031Z  |  as-of date: 2026-11-17
- Generator: offline simulator (testing only, not a real LLM)
- Policy version: `seg-v1.0|comm-v1.0|rem-v1.0|offers-2026.11|priv-v1.0`
- Data: labelled synthetic demonstration customers (not real customers).

## Summary

| Metric | Result |
|---|---|
| Classification accuracy (labelled scenarios) | 100.0% |
| End-to-end scenario pass rate | 100.0% |
| Validator catch rate (planted errors) | 100.0% |
| Caught by the expected check | 100.0% |
| False positives on clean approved templates | 0.0% |
| First-pass validation rate (incl. injected faults) | 53.3% |
| Groundedness (amounts, %, dates, numbers) | 100.0% of 15 drafts |
| Offer compliance | 100.0% |
| Consent compliance | 100.0% |
| Reviewer edit rate / rejection rate | 50.0% / 50.0% |
| Mock emails sent | 2 |

## Scenario results

| Scenario | Expected segment | Predicted | Status | Offer | Stage | Mode | Block reasons | Pass |
|---|---|---|---|---|---|---|---|---|
| A - Loyal customer | LOYAL | LOYAL | PENDING_REVIEW | LOYALTY_001 | - | llm | - | PASS |
| B - Declining customer | DECLINING | DECLINING | PENDING_REVIEW | REENGAGE_001 | - | llm | - | PASS |
| C - Dormant customer | DORMANT | DORMANT | PENDING_REVIEW | WINBACK_001 | - | llm | - | PASS |
| D - Overdue customer (stage 2) | OVERDUE | OVERDUE | PENDING_REVIEW | - | 2 | llm | - | PASS |
| D1 - Overdue customer (stage 1) | OVERDUE | OVERDUE | PENDING_REVIEW | - | 1 | llm | - | PASS |
| D3 - Overdue customer (stage 3) | OVERDUE | OVERDUE | PENDING_REVIEW | - | 3 | llm | - | PASS |
| E - No consent | LOYAL | LOYAL | BLOCKED | - | - | not_generated | NO_CONSENT | PASS |
| F - Invalid (expired) offer | LOYAL | LOYAL | PENDING_REVIEW | LOYALTY_001 | - | llm | - | PASS |
| G - Hallucinated amount | OVERDUE | OVERDUE | PENDING_REVIEW | - | 1 | repair | - | PASS |
| H - Contradictory payment data | manual review | manual review | BLOCKED | - | - | not_generated | MANUAL_REVIEW | PASS |
| I - Recently contacted | LOYAL | LOYAL | BLOCKED | - | - | not_generated | RECENT_CONTACT | PASS |
| J - Missing customer evidence | manual review | manual review | BLOCKED | - | - | not_generated | MANUAL_REVIEW | PASS |
| K - Consistent customer | CONSISTENT | CONSISTENT | PENDING_REVIEW | THANKS_001 | - | llm | - | PASS |

## Validator catch rate (planted errors)

| Planted error | Expected check | Caught | Failed checks | Retry recommended |
|---|---|---|---|---|
| Wrong amount | AMOUNT_VERIFICATION | YES | AMOUNT_VERIFICATION, UNSUPPORTED_CLAIMS | True |
| Wrong due date | DATE_VERIFICATION | YES | DATE_VERIFICATION, UNSUPPORTED_CLAIMS, REQUIRED_CONTENT | True |
| Invented tenure | UNSUPPORTED_CLAIMS | YES | UNSUPPORTED_CLAIMS | True |
| Invented discount percentage | PERCENTAGE_VERIFICATION | YES | PERCENTAGE_VERIFICATION, UNSUPPORTED_CLAIMS, OFFER_TERMS | True |
| Offer terms dropped | OFFER_TERMS | YES | OFFER_TERMS | True |
| Promo in reminder | NO_PROMO_IN_REMINDER | YES | PERCENTAGE_VERIFICATION, NO_PROMO_IN_REMINDER | True |
| Unapproved promotion | UNAPPROVED_PROMOTION | YES | UNAPPROVED_PROMOTION | True |
| Banned threat | PROHIBITED_PHRASES | YES | PROHIBITED_PHRASES | True |
| Internal label disclosed | INTERNAL_DISCLOSURE | YES | INTERNAL_DISCLOSURE | True |
| Card number leaked | PII_LEAKAGE | YES | UNSUPPORTED_CLAIMS, PII_LEAKAGE | True |
| Unknown link | PII_LEAKAGE | YES | PII_LEAKAGE | True |
| Dispute link missing | SUPPORT_CONTACT | YES | REQUIRED_CONTENT, SUPPORT_CONTACT | True |
| Unresolved placeholder | PLACEHOLDERS_RESOLVED | YES | PLACEHOLDERS_RESOLVED | True |
| Body too short | SCHEMA | YES | SCHEMA, OFFER_TERMS, REQUIRED_CONTENT, SUPPORT_CONTACT | True |

## Injected LLM faults (repair and fallback)

| Fault | Customer | Attempts (mode, passed) | Final status | Final mode |
|---|---|---|---|---|
| LLM types its own (wrong) amount instead of the verified one | DEMO-D1-OVERDUE-S1 | [('llm', False), ('repair', True)] | PENDING_REVIEW | repair |
| LLM adds a threatening phrase | DEMO-D-OVERDUE | [('llm', False), ('repair', True)] | PENDING_REVIEW | repair |
| LLM adds a discount to a payment reminder | DEMO-D3-OVERDUE-S3 | [('llm', False), ('repair', True)] | PENDING_REVIEW | repair |
| LLM returns text that is not valid JSON | DEMO-B-DECLINING | [('llm', False), ('format_retry', True)] | PENDING_REVIEW | format_retry |
| LLM drops the dispute link | DEMO-D-OVERDUE | [('llm', False), ('repair', True)] | PENDING_REVIEW | repair |
| LLM invents an unapproved discount | DEMO-K-CONSISTENT | [('llm', False), ('repair', True)] | PENDING_REVIEW | repair |

## Refusal / blocking results

- **E - No consent** (DEMO-E-NOCONSENT): BLOCKED - NO_CONSENT; the LLM was not called.
- **H - Contradictory payment data** (DEMO-H-CONTRADICTORY): BLOCKED - MANUAL_REVIEW; the LLM was not called.
- **I - Recently contacted** (DEMO-I-RECENT-CONTACT): BLOCKED - RECENT_CONTACT; the LLM was not called.
- **J - Missing customer evidence** (DEMO-J-MISSING): BLOCKED - MANUAL_REVIEW; the LLM was not called.

## Simulated reviewer session

- DEMO-D1-OVERDUE-S1: approve+send -> MOCK_SENT
- DEMO-D3-OVERDUE-S3: edit -> PENDING_REVIEW
- DEMO-B-DECLINING: reject -> REJECTED
- DEMO-D-OVERDUE: approve+send -> MOCK_SENT
- DEMO-K-CONSISTENT: edit -> PENDING_REVIEW
- DEMO-A-LOYAL: reject -> REJECTED

## Operational metrics

```json
{
  "drafts_total": 19,
  "drafts_by_status": {
    "BLOCKED": 4,
    "CANCELLED": 6,
    "MOCK_SENT": 2,
    "PENDING_REVIEW": 5,
    "REJECTED": 2
  },
  "retry_rate": 0.467,
  "fallback_template_usage": 0,
  "validation_failures_by_check": {},
  "block_reasons": {
    "MANUAL_REVIEW": 4,
    "NO_CONSENT": 1,
    "RECENT_CONTACT": 1
  },
  "tokens": {
    "input": 13821,
    "output": 2832
  },
  "estimated_cost_usd": 0.0839,
  "avg_generation_latency_ms": 5.0
}
```

## Known limitations

- Offline runs use the clearly-labelled offline simulator instead of a real LLM; with an API key the same harness exercises Claude.
- Demonstration customers are synthetic and hand-labelled; accuracy on them shows rule correctness, not real-world performance.
- Tone is checked with heuristics; the optional LLM judge is advisory and disabled in offline evaluation.
- TF-IDF retrieval is used when Sentence Transformers is unavailable; semantic recall is lower.
