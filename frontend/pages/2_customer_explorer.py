from pathlib import Path

import pandas as pd
import streamlit as st

from backend.services.bootstrap import load_csv
from frontend.utils.ui import safe_df, STRETCH, get_c, show_badge
from modules.data_engineering.data_loader import MappingError, inspect_csv

c = get_c()
st.title("Customer Explorer")

with st.expander("Upload the Kaggle CSV (customer_churn_1m.csv)"):
    up = st.file_uploader("CSV file", type=["csv"])
    limit = st.number_input("Rows to load (0 = all; the full file is loaded in 100k-row chunks)", min_value=0, value=50000,
                            step=10000)
    if up is not None and st.button("Inspect and load"):
        dest = c.settings.data_dir / "raw" / "uploads" / Path(up.name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(up.getbuffer())
        insp = inspect_csv(dest, c.settings.data_mapping)
        st.write("Columns found:", insp.columns)
        if insp.missing_mapped_columns:
            st.warning(f"Mapped columns missing from the file: {insp.missing_mapped_columns}")
        try:
            with st.spinner("Cleaning, enriching and loading ..."):
                res = load_csv(c, dest, limit=int(limit) or None)
            st.success(f"Loaded {res['loaded']:,} customers.")
            st.json(res["cleaning"])
        except MappingError as exc:
            st.error(str(exc))

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
q = f1.text_input("Search by customer ID or name", "")
segment = f2.selectbox("Segment", ["", "LOYAL", "CONSISTENT", "DECLINING", "DORMANT", "OVERDUE", "MANUAL_REVIEW", "UNCLASSIFIED"])
source = f3.selectbox("Source", ["", "demo", "sample", "kaggle"])
page_size = f4.selectbox("Rows per page", [25, 50, 100], index=1)
total = c.customers.count(segment or None, source or None, q or None)
pages = max(1, (total + page_size - 1) // page_size)
page = st.number_input(f"Page (of {pages}) · {total:,} matching customers", min_value=1, max_value=pages, value=1)
rows = c.customers.search(q or None, segment or None, source or None, limit=page_size, offset=(page - 1) * page_size)
st.dataframe(safe_df(rows), **STRETCH, hide_index=True)

ids = [r["customer_id"] for r in rows]
if not ids:
    st.stop()
current = st.session_state.get("customer_id")
cid = st.selectbox("View customer profile", ids, index=ids.index(current) if current in ids else 0)
st.session_state["customer_id"] = cid
p = c.engagement.profile(cid)

st.subheader(f"{p.customer_name}  ·  {cid}")
m = st.columns(5)
m[0].metric("Tenure (months)", p.tenure_months if p.tenure_months is not None else "missing")
m[1].metric("Monthly charges", f"${p.monthly_charges:,.2f}" if p.monthly_charges is not None else "missing")
m[2].metric("Payment status", p.payment_status or "missing")
m[3].metric("Amount due", f"${p.amount_due:,.2f}" if p.amount_due is not None else "missing")
m[4].metric("Days overdue", p.days_overdue)
m = st.columns(5)
m[0].metric("Usage last 3m (GB)", p.usage_last_3m if p.usage_last_3m is not None else "missing")
m[1].metric("Usage prev 3m (GB)", p.usage_prev_3m if p.usage_prev_3m is not None else "missing")
m[2].metric("Days since active", p.days_since_active if p.days_since_active is not None else "missing")
m[3].metric("Marketing consent", {True: "Yes", False: "No", None: "Unverified"}[p.marketing_consent])
m[4].metric("Days since contact", p.days_since_contact if p.days_since_contact is not None else "never")

if p.data_issues:
    for i in p.data_issues:
        (st.error if i.severity == "BLOCK" else st.warning)(f"{i.code}: {i.detail}")
else:
    st.success("Data quality checks passed.")

st.markdown("#### Field provenance (original vs derived vs synthetic)")
data = p.model_dump(mode="json")
prov_rows = [{"Field": f, "Value": data.get(f), "Source": src} for f, src in p.field_sources.items()]
st.dataframe(safe_df(prov_rows), **STRETCH, hide_index=True)
st.caption("Protected attributes (gender, age, senior citizen, marital status, dependents, education, income, credit score) "
           "are dropped during preprocessing and are never stored or used.")
seg = c.customers.get_segment(cid)
if seg:
    show_badge(seg.get("primary_segment") or seg.get("status"), "Last classification: ")
