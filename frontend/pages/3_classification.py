import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, badge, customer_picker, get_c

c = get_c()
st.title("Customer Classification")
st.caption("Transparent rules from policies/segmentation.yaml. All matching segments are kept; the primary segment follows "
           "the configured priority. Missing or contradictory data goes to manual review - nothing is guessed.")

cid = customer_picker(c, "cls")
st.button("Re-run classification", type="primary")  # classification is cheap; it always runs for the selected customer
if cid:
    profile, seg = c.engagement.classify(cid)
    cols = st.columns(4)
    cols[0].markdown("**Status**<br>" + badge(seg.status), unsafe_allow_html=True)
    cols[1].markdown("**Primary segment**<br>" + badge(seg.primary_segment or "none"), unsafe_allow_html=True)
    cols[2].markdown("**Secondary segments**<br>" + (" ".join(badge(s) for s in seg.secondary_segments) or "-"),
                     unsafe_allow_html=True)
    cols[3].metric("Confidence", seg.confidence)
    if seg.manual_review_reasons:
        st.warning("Manual review: " + "; ".join(seg.manual_review_reasons))
    if seg.reason_codes:
        st.write("**Reason codes:** " + ", ".join(f"`{r}`" for r in seg.reason_codes))
    if seg.churn_status_info is not None:
        st.caption(f"Dataset churn label: {seg.churn_status_info} (supplementary information only - it never decides treatment).")
    if seg.evidence:
        st.markdown("#### Evidence for each rule")
        ev = pd.DataFrame([{"Segment": e.segment, "Rule": f"{e.field} {e.operator} {e.threshold}", "Actual": e.actual,
                            "Passed": "✅" if e.passed else "❌", "Near threshold": "⚠️" if e.near_threshold else "",
                            "Reason code": e.reason_code, "Policy": e.policy_ref} for e in seg.evidence])
        st.dataframe(safe_df(ev), **STRETCH, hide_index=True)

with st.expander("Segmentation rules in force"):
    st.dataframe(safe_df(c.segmentation.describe_rules()), **STRETCH, hide_index=True)
    st.caption(f"Rule version {c.segmentation.version}. Edit policies/segmentation.yaml to change thresholds.")
