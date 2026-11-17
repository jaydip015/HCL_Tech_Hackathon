---
doc_id: POL-DISPUTE
title: Dispute and Support Escalation Policy
version: "1.0"
segments: [OVERDUE, ALL]
---
> SYNTHETIC DEMONSTRATION POLICY for the hackathon prototype. Not an actual telecom regulation or HCLTech policy.

## 1. Support channels
Customers can reach support at 1800-200-3000 or support@example-telecom.com. Billing disputes can be raised at https://www.example-telecom.com/billing/dispute.

## 2. Disputes
Every payment reminder must tell the customer how to dispute the bill. While a dispute is open, no further reminders should be sent for that bill.

## 3. Manual escalation
Cases are escalated to a human reviewer when customer data is missing or contradictory, when no segment rule applies, when classification confidence is low, or when a generated message fails validation after repair and fallback.

## 4. Reviewer responsibilities
Reviewers check the evidence, the selected strategy, the offer and the validation results, and then approve, edit, reject or request regeneration. Edited messages are validated again. A message that fails validation cannot be approved or sent.
