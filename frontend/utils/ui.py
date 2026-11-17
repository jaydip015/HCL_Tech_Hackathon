"""Shared Streamlit helpers: cached container, customer picker, badges and tables."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from backend.services.container import Container, build_container


def _stretch_kwargs() -> dict[str, Any]:
    """Newer Streamlit replaced use_container_width with width="stretch"; support both."""
    try:
        major, minor = (int(x) for x in st.__version__.split(".")[:2])
    except Exception:  # noqa: BLE001
        return {"use_container_width": True}
    return {"width": "stretch"} if (major, minor) >= (1, 50) else {"use_container_width": True}


STRETCH = _stretch_kwargs()

STATUS_COLORS = {
    "PENDING_REVIEW": "#2563eb", "APPROVED": "#059669", "MOCK_SENT": "#047857", "BLOCKED": "#dc2626",
    "NEEDS_FIX": "#d97706", "REJECTED": "#6b7280", "CANCELLED": "#6b7280", "CLASSIFIED": "#059669",
    "MANUAL_REVIEW": "#d97706", "PASS": "#059669", "FAIL": "#dc2626", "WARN": "#d97706", "SKIP": "#6b7280",
}
SEGMENT_COLORS = {"LOYAL": "#7c3aed", "CONSISTENT": "#059669", "DECLINING": "#d97706", "DORMANT": "#64748b",
                  "OVERDUE": "#dc2626", "MANUAL_REVIEW": "#b45309"}


@st.cache_resource(show_spinner="Starting services and indexing policies ...")
def get_c() -> Container:
    return build_container()


def badge(text: str | None, color: str | None = None) -> str:
    text = text or "-"
    color = color or STATUS_COLORS.get(text) or SEGMENT_COLORS.get(text, "#334155")
    return (f"<span style='background:{color};color:white;padding:2px 10px;border-radius:12px;"
            f"font-size:0.8rem;font-weight:600'>{text}</span>")


def show_badge(text: str | None, prefix: str = "") -> None:
    st.markdown(f"{prefix}{badge(text)}", unsafe_allow_html=True)


def _selectbox_accepts_typing() -> bool:
    """Streamlit 1.45+ lets a selectbox accept a typed value that is not in its options."""
    try:
        import inspect
        return "accept_new_options" in inspect.signature(st.selectbox).parameters
    except (TypeError, ValueError):
        return False


def _resolve_typed_customer(c: Container, text: str) -> str | None:
    """A customer ID typed into the dropdown: exact ID first (any case), then the first search match."""
    text = text.strip()
    for candidate in (text, text.upper()):
        if candidate and c.customers.exists(candidate):
            return candidate
    hits = c.customers.search(query=text, limit=1) if text else []
    return hits[0]["customer_id"] if hits else None


def customer_picker(c: Container, key: str, label: str = "Customer") -> str | None:
    """Search box + dropdown; either one alone is enough to find a customer.

    * Typing in the search box lists only the matching customers and selects the best match
      (an exact ID match comes first).
    * Typing a customer ID straight into the dropdown and pressing Enter also works.
    With no search, demo customers are listed, plus the customer chosen on another page.
    The selection is shared across pages through st.session_state["customer_id"].
    """
    search = st.text_input("Search customer ID or name", value="", key=f"{key}_search",
                           placeholder="e.g. DEMO-A or CUST0000000012").strip()
    current = st.session_state.get("customer_id")
    if search:
        found = c.customers.search(query=search, limit=50)
        found.sort(key=lambda r: r["customer_id"].upper() != search.upper())  # exact ID match first
        if not found:
            st.warning(f"No customer ID or name matches '{search}'.")
        rows = {r["customer_id"]: r for r in found}
    else:
        rows = {r["customer_id"]: r for r in c.customers.search(source="demo", limit=50)}
        if current and current not in rows and c.customers.exists(current):
            rows = {current: c.customers.get_row(current) or {}, **rows}
    if not rows and not search:
        st.info("No customers loaded yet. Use the Executive Dashboard setup panel or upload a CSV in Customer Explorer.")
        return None

    ids = list(rows.keys())
    index = ids.index(current) if current in ids and not (search and ids[0].upper() == search.upper()) else 0

    def fmt(i: str) -> str:
        row = rows.get(i)
        if not row:
            return i
        return f"{i} - {row.get('customer_name') or ''}" + (" (demo)" if row.get("data_source") == "demo" else "")

    typing = _selectbox_accepts_typing()
    extra = {"accept_new_options": True} if typing else {}
    # The key includes the search text, so a new search resets the dropdown to the best match
    # instead of keeping the previously selected customer.
    choice = st.selectbox(label, ids, index=index if ids else None, key=f"{key}_select_{search.upper()}",
                          format_func=fmt, placeholder="Type a customer ID and press Enter" if typing else "",
                          help="Pick from the list, or type any customer ID and press Enter." if typing else None,
                          **extra)
    if choice and choice not in rows:  # typed straight into the dropdown
        resolved = _resolve_typed_customer(c, choice)
        if not resolved:
            st.error(f"Customer '{choice}' not found.")
            return None
        choice = resolved
    if not choice:
        return None
    st.session_state["customer_id"] = choice
    return choice


def safe_df(data: Any) -> pd.DataFrame:
    """DataFrame whose object columns are plain strings, so Arrow serialisation never fails on
    mixed types, lists or dicts."""
    df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: "" if v is None else (v if isinstance(v, str) else str(v)))
    return df


def findings_df(findings: list[Any]) -> pd.DataFrame:
    rows = []
    for f in findings:
        f = f if isinstance(f, dict) else f.model_dump(mode="json")
        rows.append({"Check": f["check"], "Status": f["status"], "Severity": f.get("severity"),
                     "Category": f.get("category") or "", "Detail": f.get("detail", "")})
    return pd.DataFrame(rows)


def show_findings(findings: list[Any]) -> None:
    df = findings_df(findings)
    if df.empty:
        st.caption("No validation findings.")
        return
    fails = df[df["Status"] == "FAIL"]
    warns = df[df["Status"] == "WARN"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Checks passed", int((df["Status"] == "PASS").sum()))
    c2.metric("Blocking failures", int(((df["Status"] == "FAIL") & (df["Severity"] == "BLOCK")).sum()))
    c3.metric("Warnings", int(len(warns)))
    if not fails.empty:
        st.error("Failed checks:\n\n" + "\n".join(f"- **{r.Check}** ({r.Category}): {r.Detail}" for r in fails.itertuples()))
    if not warns.empty:
        st.warning("Warnings (advisory):\n\n" + "\n".join(f"- **{r.Check}**: {r.Detail}" for r in warns.itertuples()))
    st.dataframe(safe_df(df), **STRETCH, hide_index=True)


def email_preview(subject: str, body: str, cta: str = "") -> None:
    safe_body = (body or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    safe_subject = (subject or "").replace("<", "&lt;")
    st.markdown(
        f"""<div style='border:1px solid #cbd5e1;border-radius:10px;padding:16px;background:#ffffff;color:#0f172a'>
        <div style='font-size:0.8rem;color:#64748b'>Subject</div>
        <div style='font-weight:700;margin-bottom:10px'>{safe_subject}</div>
        <div style='line-height:1.55'>{safe_body}</div>
        {f"<div style='margin-top:12px'><span style='background:#0ea5e9;color:white;padding:6px 14px;border-radius:6px'>{cta}</span></div>" if cta else ""}
        </div>""", unsafe_allow_html=True)


def bar_chart(data: dict[str, int | float], title: str, color_map: dict[str, str] | None = None) -> None:
    if not data:
        st.caption(f"{title}: no data yet")
        return
    df = pd.DataFrame({"label": list(data.keys()), "value": list(data.values())})
    try:
        import plotly.express as px  # type: ignore

        fig = px.bar(df, x="label", y="value", title=title, color="label",
                     color_discrete_map=color_map or {}, text="value")
        fig.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, **STRETCH)
    except ImportError:
        st.caption(title)
        st.bar_chart(df.set_index("label"))


def sidebar_status(c: Container) -> None:
    with st.sidebar:
        st.markdown("### System status")
        st.caption(f"LLM: {c.llm_status}")
        st.caption(f"RAG: {c.retriever.stats()['embedder']} / {c.retriever.stats()['vector_store']}")
        st.caption(f"As-of date: {c.settings.as_of_date}")
        st.caption(f"Policy: {c.settings.policy_version}")
        st.caption("Mock delivery only. No real emails are sent.")
