import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, get_c
from modules.evaluation.evaluation import run_evaluation, to_markdown

c = get_c()
st.title("Evaluation")
st.caption("Runs every labelled scenario, planted validator errors and injected LLM faults in an ISOLATED database "
           "(your review data is untouched) and produces reports/evaluation_report.md.")
provider = st.radio("Generator for the evaluation", ["offline_simulator", "auto", "none"], horizontal=True,
                    help="offline_simulator needs no API key; auto uses the configured LLM; none = static templates only")
if st.button("Run evaluation", type="primary"):
    with st.spinner("Running scenarios ..."):
        st.session_state["eval"] = run_evaluation(c.settings, provider)

r = st.session_state.get("eval")
if not r:
    st.stop()
pct = lambda v: "-" if v is None else f"{v * 100:.1f}%"  # noqa: E731
k = st.columns(4)
k[0].metric("Classification accuracy", pct(r["classification_accuracy"]))
k[1].metric("Scenario pass rate", pct(r["scenario_pass_rate"]))
k[2].metric("Validator catch rate", pct(r["validator_catch_rate"]))
k[3].metric("False positives (clean)", pct(r["false_positive_rate_on_clean_templates"]))
k = st.columns(4)
k[0].metric("Groundedness", pct(r["groundedness_rate"]))
k[1].metric("Offer compliance", pct(r["offer_compliance_rate"]))
k[2].metric("Consent compliance", pct(r["consent_compliance_rate"]))
k[3].metric("First-pass rate", pct(r["metrics"]["first_pass_validation_rate"]))
st.markdown("#### Scenarios")
st.dataframe(safe_df([{k2: s[k2] for k2 in ("scenario", "expected_segment", "predicted_segment", "status", "offer", "stage",
                                                 "mode", "block_reasons", "passed")} for s in r["scenarios"]]),
             **STRETCH, hide_index=True)
st.markdown("#### Validator: planted errors")
st.dataframe(safe_df(r["validator_cases"]), **STRETCH, hide_index=True)
st.markdown("#### Injected LLM faults")
st.dataframe(safe_df(r["fault_injection"]), **STRETCH, hide_index=True)
st.download_button("Download evaluation_report.md", to_markdown(r), file_name="evaluation_report.md", mime="text/markdown")
