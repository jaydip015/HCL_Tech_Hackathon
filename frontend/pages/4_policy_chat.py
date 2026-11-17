import streamlit as st

from frontend.utils.ui import badge, customer_picker, get_c

c = get_c()
st.title("Policy Chat (RAG)")
st.caption("Pick a customer to see which category they belong to and the policy proof behind it. "
           "Categories come from the deterministic rules; the policy text is quoted, never generated.")

cid = customer_picker(c, "qa")


def quote(q, label: str | None = None, expanded: bool = False) -> None:
    """Show one policy section, quoted word for word from the knowledge base."""
    if q is None:
        st.caption("No matching policy section found in the knowledge base.")
        return
    with st.expander(f"📄 {label or 'Policy proof'}: {q.ref} (v{q.version})", expanded=expanded):
        st.markdown(f"**{q.doc_name} - {q.section}**")
        st.markdown("\n".join(f"> {line}" if line.strip() else ">" for line in q.text.splitlines()))
        st.caption(f"Source: {q.doc_id}, knowledge_base/policies")


overview_tab, chat_tab = st.tabs(["Customer overview", "Ask a question"])

with overview_tab:
    if cid:
        ov = c.overview.overview(cid)
        category = ov.primary_segment if ov.status == "CLASSIFIED" else "MANUAL_REVIEW"
        st.markdown(f"### {cid} {badge(category)}", unsafe_allow_html=True)
        (st.success if ov.status == "CLASSIFIED" else st.warning)(ov.headline)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Category", category)
        m2.metric("Confidence", f"{ov.confidence:.2f}")
        m3.metric("Next action", ov.objective or ("Blocked" if ov.blocked else "-"))
        m4.metric("Also matches", ", ".join(ov.secondary_segments) or "-")

        with st.expander("Customer facts used by the rules"):
            st.table({"Fact": list(ov.key_facts), "Value": list(ov.key_facts.values())})
            st.caption(f"Data source: {ov.data_source} · rules version {ov.policy_version}")
            for issue in ov.data_issues:
                st.warning(f"Data issue: {issue}")

        st.subheader("Why this category: rule checks with policy proof")
        st.caption("Each category is checked in policy priority order: " + " > ".join(ov.priority)
                   + ". The first category whose rules are all met becomes the primary category.")
        for chk in ov.segment_checks:
            if not chk.evaluated:
                icon, state = "⚪", "not checked (data missing)"
            elif chk.matched:
                icon, state = "✅", "PRIMARY CATEGORY" if chk.is_primary else "also matches"
            else:
                icon, state = "❌", "not met"
            with st.container(border=True):
                st.markdown(f"#### {icon} {chk.segment} · {state}")
                if chk.description:
                    st.caption(chk.description)
                for cond in chk.conditions:
                    st.markdown(f"{'✔️' if cond.passed else '✖️'} `{cond.reason_code}`: {cond.explanation}")
                quote(chk.policy, expanded=chk.is_primary)

        if ov.manual_review_reasons:
            st.subheader("Why this customer needs manual review")
            for r in ov.manual_review_reasons:
                with st.container(border=True):
                    st.markdown(f"⚠️ {r.reason}")
                    quote(r.policy, expanded=True)
        if ov.status == "CLASSIFIED" and ov.secondary_segments:
            quote(ov.priority_policy, "Priority rule")

        st.subheader("What the policy says to do next")
        n1, n2, n3 = st.columns(3)
        n1.metric("Objective", ov.objective or "-")
        n2.metric("Tone", ov.tone or "-")
        n3.metric("Offer / stage", ov.offer or (f"Reminder stage {ov.reminder_stage}" if ov.reminder_stage else "-"))
        if ov.blocked:
            st.error("Outreach is blocked for this customer.")
            for r in ov.block_reasons:
                with st.container(border=True):
                    st.markdown(f"⛔ {r.reason}")
                    quote(r.policy, expanded=True)
        for q in ov.strategy_policies:
            quote(q, "Treatment policy")

with chat_tab:
    SAMPLES = [
        "Why was this customer classified as LOYAL?",
        "Is this customer eligible for a loyalty offer?",
        "Why was a promotional email blocked?",
        "What communication tone should be used?",
        "Can this customer receive an engagement offer?",
        "Why is this customer receiving a payment reminder?",
        "Which policy supports this decision?",
    ]
    st.caption("Answers use only the selected customer's verified decision evidence plus retrieved policy excerpts. "
               "Policies explain decisions; they never override the deterministic rules.")
    sample = st.selectbox("Example questions", [""] + SAMPLES)
    question = st.text_input("Ask a question about this customer", value=sample)
    history = st.session_state.setdefault("qa_history", [])

    if cid and st.button("Ask", type="primary") and question.strip():
        with st.spinner("Retrieving policy evidence ..."):
            ans = c.policy_qa.answer(cid, question)
        history.insert(0, ans)

    for ans in history[:10]:
        with st.container(border=True):
            st.markdown(f"**{ans.customer_id} · Q:** {ans.question}")
            if ans.insufficient_evidence:
                st.warning(ans.answer)
            else:
                st.markdown(ans.answer)
            st.caption(f"Answer mode: {ans.mode}" + (f" ({ans.model_name})" if ans.model_name else ""))
            for s in ans.sources:
                with st.expander(f"📄 {s.doc_name} - {s.section} (v{s.version}, score {s.score})"):
                    st.write(s.excerpt)
    if history and st.button("Clear history"):
        st.session_state["qa_history"] = []
        st.rerun()
