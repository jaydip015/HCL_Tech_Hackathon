# Demo scenarios

## Setup

1. Run `python scripts/setup_all.py`.
2. Run `streamlit run app.py`.
3. Open **Executive Dashboard → Setup → Load demo customers**.

In the UI, select a demo customer on any page; the selection carries over to every other page. From the terminal, `python scripts/demo_e2e.py --send` runs all scenarios at once.

| Case | Customer | What to show | Expected result |
|---|---|---|---|
| **A: Loyal** | DEMO-A-LOYAL (48 months tenure, pays on time, consented) | Classification → Offer and Strategy → Email Generator → Human Review → Approve → Mock send → Audit | LOYAL (secondary: CONSISTENT), LOYALTY_001 (10% discount), warm email, validation passes, MOCK_SENT. Generating again afterwards is **blocked** by RECENT_CONTACT and DUPLICATE_OUTREACH. |
| **B: Declining** | DEMO-B-DECLINING (310 GB → 82 GB) | Classification evidence (USAGE_DROP_GT_40PCT) | DECLINING, REENGAGE_001, friendly tone |
| **C: Dormant** | DEMO-C-DORMANT (100 days inactive) | Strategy | DORMANT, REACTIVATE, WINBACK_001 |
| **D: Overdue** | DEMO-D-OVERDUE (20 days, $134.40, tenure 40) | Classification shows OVERDUE + LOYAL. The strategy note explains why the loyal reward is ignored. | Stage 2 firm reminder with amount, due date, phone and dispute link. **No offer.** DEMO-D1 (7 days) gets stage 1; DEMO-D3 (45 days, partial payment) gets stage 3. |
| **E: No consent** | DEMO-E-NOCONSENT | Email Generator; Policy Chat: "Why was a promotional email blocked?" | BLOCKED (NO_CONSENT), LLM not called, reason displayed, answer cites Marketing Consent Policy §3 |
| **F: Invalid offer** | DEMO-F-EXPIRED-OFFER | Email Generator → Demo options → force LOYALTY_2025 | The expired offer is rejected, a note explains why, and the strategy is recomputed with LOYALTY_001. The validator also rejects expired offers directly (see Evaluation → planted errors). |
| **G: Hallucinated amount** | DEMO-G-HALLUCINATION | Email Generator → inject `wrong_amount` | Attempt 1 fails AMOUNT_VERIFICATION ($1,500.00 vs $79.99). The repair prompt fixes it, so attempt 2 passes. A failing draft can never be approved. |
| **H: Contradictory payment** | DEMO-H-CONTRADICTORY (PAID with $45 due) | Customer Explorer shows the data issue. Email Generator. | Data failure: MANUAL_REVIEW, no reminder generated, escalation reason shown |
| Extra: recently contacted | DEMO-I-RECENT-CONTACT (2 days ago) | Strategy | BLOCKED by RECENT_CONTACT (7-day cooldown) |
| Extra: missing evidence | DEMO-J-MISSING | Classification | MANUAL_REVIEW listing the missing tenure, usage and activity; no segment is fabricated |
| Extra: consistent | DEMO-K-CONSISTENT | Generator | APPRECIATION + THANKS_001 |

## Reviewer rules to demonstrate

| Action | Expected result |
|---|---|
| Edit a reminder and change $134.40 to $13.44 | NEEDS_FIX; approval disabled |
| Change it back | PENDING_REVIEW |
| Mark a customer as paid in the database after approving their reminder, then press Mock send | CANCELLED (pre-send gate) |
| Press Mock send twice | The second press is refused (ALREADY_DELIVERED) |
| Reject without a reason | Refused |
| Regenerate with the feedback "make it warmer" | New draft created; the old one is CANCELLED |
