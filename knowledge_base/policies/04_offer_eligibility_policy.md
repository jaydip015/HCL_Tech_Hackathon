---
doc_id: POL-OFFERS
title: Offer Eligibility Policy
version: "1.0"
segments: [LOYAL, CONSISTENT, DECLINING, DORMANT]
---
> SYNTHETIC DEMONSTRATION POLICY for the hackathon prototype. Not an actual telecom regulation or HCLTech policy.

## 1. Approved catalog only
Only offers in the approved offer catalog may be communicated. Offers must never be invented, changed, combined or improved by a writer or by an AI system. At most one offer may be included per message.

## 2. Eligibility checks
An offer is eligible only when all of the following are true: the offer status is ACTIVE; today's date is between the start date and the expiry date; the customer's segment is in the offer's eligible segments; the customer meets the minimum tenure; the channel EMAIL is allowed; the customer has marketing consent; and the customer is not overdue.

## 3. Expired offers
An expired offer must never appear in an email. If an expired offer was assigned, the strategy is recomputed with a valid offer, or the message proceeds without an offer, or it is blocked.

## 4. Engagement and win-back offers
Customers with declining activity may receive REENGAGE_001 (Welcome Back Offer, 5 GB bonus data). Dormant customers may receive WINBACK_001 (Win-Back Offer, 20% discount). Consistent customers may receive THANKS_001 (Thank You Bonus) as an optional thank-you.

## 5. Overdue customers
Customers with an overdue bill must never receive promotional offers, regardless of any other segment.

## 6. Stating an offer
Every email with an offer must state the offer value, the terms and the expiry date exactly as in the catalog.
