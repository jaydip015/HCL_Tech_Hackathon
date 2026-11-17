import streamlit as st

from backend.services.bootstrap import classify_all, load_demo_customers, load_sample_dataset
from frontend.utils.ui import STRETCH, SEGMENT_COLORS, bar_chart, get_c
from modules.audit.metrics import compute_metrics

c = get_c()
st.markdown("<div class='hero'><h2 style='color:white;margin:0'>Customer Loyalty and Engagement Assistant</h2>"
            "Python decides eligibility · RAG retrieves policy · the LLM writes · validators enforce · humans approve</div>",
            unsafe_allow_html=True)

total = c.customers.count()
with st.expander("Setup and data loading", expanded=total == 0):
    st.write("Load the labelled demo customers (scenarios A-K) and optionally a dataset. To use the real Kaggle file, "
             "upload it on the **Customer Explorer** page or run `python scripts/load_database.py --csv ...`.")
    col1, col2, col3 = st.columns(3)
    if col1.button("Load demo customers", **STRETCH):
        n = len(load_demo_customers(c))
        st.success(f"Loaded {n} demo customers.")
    sample_rows = col2.number_input("Sample rows (local stand-in, not Kaggle data)", min_value=100, max_value=200000,
                                    value=5000, step=1000)
    if col2.button("Generate and load sample dataset", **STRETCH):
        with st.spinner("Generating, cleaning, enriching and loading ..."):
            res = load_sample_dataset(c, int(sample_rows))
        st.success(f"Loaded {res['loaded']:,} sample customers.")
    if col3.button("Classify all customers", **STRETCH):
        bar = st.progress(0.0, text="Classifying ...")
        total_now = max(c.customers.count(), 1)
        counts = classify_all(c, progress=lambda n: bar.progress(min(n / total_now, 1.0), text=f"Classified {n:,}"))
        st.success(f"Classified: {counts}")

m = compute_metrics(c.db, c.settings.price_input_per_mtok, c.settings.price_output_per_mtok)
k = st.columns(6)
k[0].metric("Total customers", f"{m['total_customers']:,}")
k[1].metric("Customers classified", f"{m['customers_processed']:,}")
k[2].metric("Drafts generated", m["drafts_generated"])
fp = m["first_pass_validation_rate"]
k[3].metric("First-pass validation", "-" if fp is None else f"{fp * 100:.0f}%")
reviewed = m["approved"] + m["rejected"]
k[4].metric("Approval rate", "-" if not reviewed else f"{m['approved'] / reviewed * 100:.0f}%")
k[5].metric("Mock emails sent", m["mock_emails_sent"])

left, right = st.columns(2)
with left:
    bar_chart(m["customers_per_segment"], "Customers per primary segment", SEGMENT_COLORS)
with right:
    bar_chart(m["drafts_by_status"], "Drafts by status")
left, right = st.columns(2)
with left:
    bar_chart(m["offers_selected"], "Offers selected in drafts")
with right:
    bar_chart(m["block_reasons"], "Why drafts were blocked")
st.caption(f"Customers by source: {c.customers.source_counts()}  ·  'sample' rows are a local stand-in, 'demo' rows are "
           "hand-labelled scenarios, 'kaggle' rows come from the uploaded dataset (with synthetic enrichment).")
