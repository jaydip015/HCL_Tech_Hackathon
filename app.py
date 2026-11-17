"""Streamlit entry point. Run: streamlit run app.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from frontend.utils.ui import get_c, sidebar_status  # noqa: E402

st.set_page_config(page_title="Customer Engagement Assistant", page_icon="📶", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 1.6rem;}
    [data-testid="stMetricValue"] {font-size: 1.7rem;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg,#0f172a 0%,#1e293b 100%);}
    [data-testid="stSidebar"] * {color: #e2e8f0 !important;}
    h1, h2, h3 {color: #0f172a;}
    .hero {background: linear-gradient(90deg,#0ea5e9,#6366f1); color: white; padding: 14px 20px;
           border-radius: 12px; margin-bottom: 12px;}
    </style>""",
    unsafe_allow_html=True,
)

PAGES = Path(__file__).resolve().parent / "frontend" / "pages"
pages = [
    st.Page(str(PAGES / "1_executive_dashboard.py"), title="Executive Dashboard", icon="📊", default=True),
    st.Page(str(PAGES / "2_customer_explorer.py"), title="Customer Explorer", icon="🔎"),
    st.Page(str(PAGES / "3_classification.py"), title="Customer Classification", icon="🏷️"),
    st.Page(str(PAGES / "4_policy_chat.py"), title="Policy Chat (RAG)", icon="📚"),
    st.Page(str(PAGES / "5_offer_strategy.py"), title="Offer and Strategy", icon="🎁"),
    st.Page(str(PAGES / "6_email_generator.py"), title="Email Generator", icon="✉️"),
    st.Page(str(PAGES / "7_human_review.py"), title="Human Review", icon="✅"),
    st.Page(str(PAGES / "8_audit_observability.py"), title="Audit and Observability", icon="🧾"),
    st.Page(str(PAGES / "9_evaluation.py"), title="Evaluation", icon="🧪"),
]
nav = st.navigation(pages)
sidebar_status(get_c())
nav.run()
