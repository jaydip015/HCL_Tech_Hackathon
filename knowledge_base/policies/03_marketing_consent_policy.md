---
doc_id: POL-CONSENT
title: Marketing Consent Policy
version: "1.0"
segments: [LOYAL, CONSISTENT, DECLINING, DORMANT]
---
> SYNTHETIC DEMONSTRATION POLICY for the hackathon prototype. Not an actual telecom regulation or HCLTech policy.

## 1. Consent requirement
Promotional and marketing emails, including appreciation, reward, re-engagement and reactivation messages, may only be sent to customers with verified marketing consent. If consent is missing or not recorded, it is treated as no consent.

## 2. What is still allowed without consent
Service and billing messages, such as payment reminders, are not marketing and may be sent without marketing consent. They must not contain any promotional content.

## 3. Blocking
When a customer has no marketing consent, the system blocks promotional generation (block code NO_CONSENT), shows the reason to the reviewer and records it in the audit log. No offer may be attached.

## 4. Withdrawal
A customer who withdraws consent must not receive further marketing. The latest recorded consent always applies.
