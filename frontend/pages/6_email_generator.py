import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, badge, customer_picker, email_preview, get_c, show_findings
from modules.generation.simulators import FAULTS

c = get_c()
st.title("Email Generator")
st.caption(f"Generator: **{c.llm_status}**. The LLM only writes wording using placeholders for verified facts; "
           "every draft is validated before it reaches review.")

cid = customer_picker(c, "gen")
if not cid:
    st.stop()
with st.expander("Demo and test options"):
    forced = st.selectbox("Force-assign an offer (scenario F: try LOYALTY_2025, which has expired)",
                          [""] + [o.offer_id for o in c.offers.all()])
    fault = st.selectbox("Inject an LLM fault into the first attempt (scenario G)", [""] + list(FAULTS),
                         format_func=lambda f: f"{f} - {FAULTS[f]}" if f else "none")
    if fault and not c.provider.available:
        st.caption("No LLM configured: the clearly-labelled offline simulator produces the faulty first reply.")
    supersede = st.checkbox("Replace an existing open draft for this customer", value=False)

if st.button("Generate draft", type="primary"):
    with st.spinner("Classifying, selecting strategy, retrieving policy, generating and validating ..."):
        d = c.engagement.create_draft(cid, forced_offer_id=forced or None, fault=fault or None, supersede=supersede,
                                      actor="ui")
    st.session_state["last_draft_id"] = d.draft_id

draft_id = st.session_state.get("last_draft_id")
d = c.drafts.get(draft_id) if draft_id else None
if d is None or d.customer_id != cid:
    open_d = c.drafts.open_draft_for(cid)
    d = open_d
if d is None:
    st.info("No draft yet for this customer.")
    st.stop()

st.markdown(f"**Draft {d.draft_id}** " + badge(d.status.value) + f" &nbsp; mode: `{d.generation_mode}` · "
            f"model: `{d.model_name}` · prompt: `{d.prompt_version}` · policy: `{d.policy_version}`", unsafe_allow_html=True)
if d.block_reasons:
    st.error("Blocked:\n\n" + "\n".join(f"- **{b.get('code')}**: {b.get('detail')}" for b in d.block_reasons))
for n in d.strategy.get("notes", []):
    st.info(n)
if d.body:
    left, right = st.columns([3, 2])
    with left:
        email_preview(d.subject, d.body, d.cta)
    with right:
        st.markdown("**Offer**: " + (d.offer_id or "none"))
        st.markdown("**Facts used**")
        st.json(d.facts_used)
attempts = c.drafts.attempts(d.draft_id)
if attempts:
    st.markdown("#### Generation attempts")
    st.dataframe(safe_df([{"#": a["attempt_no"], "Mode": a["mode"], "Model": a["model_name"], "Prompt": a["prompt_version"],
                                "Passed": "✅" if a["passed"] else "❌", "Failure categories": a["failure_categories_json"],
                                "Latency ms": a["latency_ms"], "Tokens in/out": f"{a['input_tokens']}/{a['output_tokens']}",
                                "Error": a["error"] or ""} for a in attempts]), **STRETCH, hide_index=True)
rep = c.drafts.latest_validation(d.draft_id)
if rep:
    st.markdown("#### Validation")
    show_findings(rep.findings)
st.caption("Next: open **Human Review** in the sidebar to approve, edit, reject or regenerate this draft.")
