---
doc_id: POL-SEGMENTATION
title: Customer Segmentation Policy
version: "1.0"
segments: [OVERDUE, DORMANT, DECLINING, LOYAL, CONSISTENT]
---
> SYNTHETIC DEMONSTRATION POLICY for the hackathon prototype. Not an actual telecom regulation or HCLTech policy.

## 1. Principles
Customers are grouped by transparent, rule-based segments so that every communication decision can be explained. All matching segments are recorded with reason codes. The primary segment is chosen by priority: OVERDUE, then DORMANT, then DECLINING, then LOYAL, then CONSISTENT. A churn prediction score may be displayed for information but must never decide how a customer is treated.

## 2.1 Overdue
A customer is OVERDUE when a verified unpaid or partially paid bill is past its due date (days overdue greater than 0). Reason code: OVERDUE_GT_0D.

## 2.2 Dormant
A customer is DORMANT when there has been no recorded activity for 90 days or more. Reason code: INACTIVE_GE_90D.

## 2.3 Declining activity
A customer is DECLINING when usage in the last 3 months is less than 60% of usage in the previous 3 months, and previous usage was above zero. Reason codes: HAS_PRIOR_USAGE and USAGE_DROP_GT_40PCT.

## 2.4 Loyal
A customer is LOYAL when tenure is 36 months or more. Reason code: TENURE_GE_36M.

## 2.5 Consistent
A customer is CONSISTENT when at least 95% of bills were paid on time and the customer was active in the last 30 days. Reason codes: ON_TIME_GE_95PCT and ACTIVE_LT_30D.

## 3. Missing or contradictory data
If required data is missing (tenure, activity, usage, payment status) or contradictory (for example, a bill marked PAID with an outstanding amount), no segment is assigned. The customer is sent to manual review. Classifications must never be guessed or fabricated.

## 4. Confidence
Confidence starts at 1.0 and is reduced when values are very close to a threshold. Customers with confidence below 0.6 go to manual review.
