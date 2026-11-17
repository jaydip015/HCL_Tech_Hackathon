import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, bar_chart, get_c
from modules.audit.metrics import compute_metrics

c = get_c()
st.title("Audit and Observability")
m = compute_metrics(c.db, c.settings.price_input_per_mtok, c.settings.price_output_per_mtok)

pct = lambda v: "-" if v is None else f"{v * 100:.0f}%"  # noqa: E731
k = st.columns(6)
k[0].metric("Drafts generated", m["drafts_generated"])
k[1].metric("First-pass validation", pct(m["first_pass_validation_rate"]))
k[2].metric("Validation failure rate", pct(m["validation_failure_rate"]))
k[3].metric("Retry rate", pct(m["retry_rate"]))
k[4].metric("Fallback templates", m["fallback_template_usage"])
k[5].metric("Mock emails sent", m["mock_emails_sent"])
k = st.columns(6)
k[0].metric("Approved", m["approved"])
k[1].metric("Rejected", m["rejected"])
k[2].metric("Blocked", m["blocked"])
k[3].metric("Avg LLM latency (ms)", m["avg_generation_latency_ms"] or "-")
k[4].metric("Tokens in / out", f"{m['tokens']['input']:,} / {m['tokens']['output']:,}")
k[5].metric("Est. cost (USD)", f"${m['estimated_cost_usd']:.4f}")
l, r = st.columns(2)
with l:
    bar_chart(m["validation_failures_by_check"], "Validation failures by check")
with r:
    bar_chart(m["review_actions"], "Reviewer actions")

st.markdown("### Draft-level trace")
drafts = c.drafts.list(limit=300)
if drafts:
    did = st.selectbox("Draft", [d.draft_id for d in drafts],
                       format_func=lambda i: next(f"{i} · {d.customer_id} · {d.status.value}" for d in drafts if d.draft_id == i))
    tr = c.audit.trace(did)
    st.markdown("**Audit record**")
    st.json(tr["record"])
    t1, t2, t3, t4 = st.tabs(["Events", "Generation attempts", "Validation reports", "Reviewer actions"])
    with t1:
        st.dataframe(safe_df([{**{k: e[k] for k in ("created_at", "event", "actor")}, "payload": str(e["payload"])[:300]}
                                   for e in tr["events"]]), **STRETCH, hide_index=True)
    with t2:
        st.dataframe(safe_df(tr["attempts"]), **STRETCH, hide_index=True)
    with t3:
        for v in tr["validations"]:
            st.markdown(f"**{v['source']}** · {'PASS' if v['passed'] else 'FAIL'} · {v['created_at']}")
            st.dataframe(safe_df(v["findings"]), **STRETCH, hide_index=True)
    with t4:
        st.dataframe(safe_df(tr["reviews"]), **STRETCH, hide_index=True)

st.markdown("### Recent audit events")
st.dataframe(safe_df([{**{k: e[k] for k in ("created_at", "draft_id", "customer_id", "event", "actor")},
                            "payload": str(e["payload"])[:200]} for e in c.audit.events(limit=200)]),
             **STRETCH, hide_index=True)
st.markdown("### Mock outbox")
st.dataframe(safe_df(c.email.outbox()), **STRETCH, hide_index=True)
st.caption("Names and email addresses are redacted in audit payloads; delivery addresses are masked.")
