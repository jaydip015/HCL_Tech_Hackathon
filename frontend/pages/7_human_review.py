import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, badge, email_preview, get_c, show_findings
from modules.email.mock_email_service import DeliveryError
from modules.review.review_service import ReviewError

c = get_c()
st.title("Human Review")
reviewer = st.text_input("Reviewer name", value=st.session_state.get("reviewer", "reviewer-1"))
st.session_state["reviewer"] = reviewer

statuses = st.multiselect("Show statuses", ["PENDING_REVIEW", "NEEDS_FIX", "BLOCKED", "APPROVED", "MOCK_SENT", "REJECTED", "CANCELLED"],
                          default=["PENDING_REVIEW", "NEEDS_FIX", "BLOCKED", "APPROVED"])
queue = c.review.queue(statuses or None)
if not queue:
    st.info("The review queue is empty. Generate drafts on the Email Generator page.")
    st.stop()
st.dataframe(safe_df([{"Draft": d.draft_id, "Customer": d.customer_id, "Status": d.status.value, "Objective": d.objective,
                            "Offer": d.offer_id, "Mode": d.generation_mode, "Attempts": d.attempt_count,
                            "Updated": d.updated_at} for d in queue]), **STRETCH, hide_index=True)
ids = [d.draft_id for d in queue]
sel = st.session_state.get("review_draft")
draft_id = st.selectbox("Select draft", ids, index=ids.index(sel) if sel in ids else 0,
                        format_func=lambda i: next(f"{i} · {d.customer_id} · {d.status.value}" for d in queue if d.draft_id == i))
st.session_state["review_draft"] = draft_id
d = c.drafts.get(draft_id)
profile = c.engagement.profile(d.customer_id)
seg, strat = d.segment, d.strategy

st.markdown(f"### {d.draft_id} " + badge(d.status.value), unsafe_allow_html=True)
a, b, cc = st.columns(3)
with a:
    st.markdown("**Customer**")
    st.write({"id": profile.customer_id, "first name": profile.first_name, "tenure": profile.tenure_months,
              "payment": profile.payment_status, "amount due": profile.amount_due, "days overdue": profile.days_overdue,
              "consent": profile.marketing_consent, "days since contact": profile.days_since_contact})
with b:
    st.markdown("**Segment** " + badge(seg.get("primary_segment") or seg.get("status")), unsafe_allow_html=True)
    st.write({"all segments": seg.get("segments"), "reason codes": seg.get("reason_codes"),
              "confidence": seg.get("confidence"), "manual review": seg.get("manual_review_reasons")})
with cc:
    st.markdown("**Strategy**")
    st.write({"objective": strat.get("objective"), "tone": strat.get("tone"), "template": strat.get("template_id"),
              "stage": strat.get("reminder_stage"), "offer": d.offer_id, "notes": strat.get("notes"),
              "policy refs": strat.get("policy_refs")})
if d.block_reasons:
    st.error("Block reasons:\n\n" + "\n".join(f"- **{x.get('code')}**: {x.get('detail')}" for x in d.block_reasons))
if d.body:
    email_preview(d.subject, d.body, d.cta)
rep = c.drafts.latest_validation(d.draft_id)
with st.expander("Validation results", expanded=bool(rep and not rep.passed)):
    if rep:
        show_findings(rep.findings)
    else:
        st.caption("Not validated (blocked before generation).")
with st.expander("Generation attempts and evidence"):
    st.dataframe(safe_df(c.drafts.attempts(d.draft_id)), **STRETCH, hide_index=True)
    st.json({"facts_used": d.facts_used, "segment_evidence": seg.get("evidence", [])})

st.markdown("### Actions")
can_approve, why = c.review.can_approve(d.draft_id)
col1, col2 = st.columns(2)
with col1:
    if st.button("✅ Approve", disabled=not can_approve, help=None if can_approve else why, **STRETCH):
        try:
            c.review.approve(d.draft_id, reviewer)
            st.success("Approved.")
            st.rerun()
        except ReviewError as exc:
            st.error(str(exc))
    if not can_approve:
        st.caption(f"Approval disabled: {why}")
with col2:
    ok, problems, _ = c.email.pre_send_checks(d.draft_id)
    if st.button("📤 Mock send", disabled=not ok, **STRETCH):
        try:
            res = c.email.send(d.draft_id, reviewer)
            st.success(f"MOCK_SENT · message {res['message_id']} to {res['to']}")
        except DeliveryError as exc:
            st.error(str(exc))
    if not ok:
        st.caption("Send disabled: " + "; ".join(problems))

if d.body and d.status.value not in ("MOCK_SENT", "REJECTED", "CANCELLED") and d.generation_mode != "not_generated":
    with st.form("edit_form"):
        st.markdown("**Edit draft** (every edit is re-validated)")
        subj = st.text_input("Subject", value=d.subject)
        body = st.text_area("Body", value=d.body, height=260)
        cta = st.text_input("Call to action", value=d.cta)
        if st.form_submit_button("Save edit and re-validate"):
            try:
                nd, report = c.review.edit(d.draft_id, reviewer, subj, body, cta)
                (st.success if report.passed else st.error)(f"Re-validation {'passed' if report.passed else 'failed'}: "
                                                           f"status is now {nd.status.value}.")
            except (ReviewError, ValueError) as exc:
                st.error(str(exc))
if d.status.value not in ("MOCK_SENT", "REJECTED", "CANCELLED"):
    r1, r2 = st.columns(2)
    with r1.form("reject_form"):
        reason = st.text_input("Rejection reason")
        if st.form_submit_button("❌ Reject"):
            try:
                c.review.reject(d.draft_id, reviewer, reason)
                st.warning("Rejected.")
            except ReviewError as exc:
                st.error(str(exc))
    with r2.form("regen_form"):
        feedback = st.text_input("Feedback for regeneration (e.g. 'make it warmer')")
        if st.form_submit_button("🔁 Regenerate with feedback"):
            try:
                nd = c.review.regenerate(d.draft_id, reviewer, feedback)
                st.session_state["review_draft"] = nd.draft_id
                st.success(f"New draft {nd.draft_id} ({nd.status.value}).")
            except ReviewError as exc:
                st.error(str(exc))
