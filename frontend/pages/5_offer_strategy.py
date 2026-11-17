import pandas as pd
import streamlit as st

from frontend.utils.ui import safe_df, STRETCH, badge, customer_picker, get_c

c = get_c()
st.title("Offer and Strategy")

with st.expander("Approved offer catalog", expanded=False):
    st.caption(f"Catalog version {c.offers.version} · global rules: {c.offers.rules}")
    st.dataframe(safe_df([o.model_dump(mode="json") for o in c.offers.all()]), **STRETCH, hide_index=True)

cid = customer_picker(c, "strat")
if not cid:
    st.stop()
offer_ids = [""] + [o.offer_id for o in c.offers.all()]
forced = st.selectbox("Test: force-assign an offer (it is still checked by the eligibility rules)", offer_ids)
profile, seg, st_, history = c.engagement.decide(cid, forced or None)

cols = st.columns(5)
cols[0].markdown("**Primary segment**<br>" + badge(seg.primary_segment or seg.status), unsafe_allow_html=True)
cols[1].metric("Objective", st_.objective or "-")
cols[2].metric("Tone", st_.tone or "-")
cols[3].metric("Template", st_.template_id or "-")
cols[4].metric("Reminder stage", st_.reminder_stage or "-")

if st_.blocked:
    st.error("Communication blocked:\n\n" + "\n".join(f"- **{b.code}** ({b.category.value}): {b.detail}"
                                                     + (f" - *{b.policy_ref}*" if b.policy_ref else "") for b in st_.block_reasons))
else:
    st.success("Strategy allowed" + (f" with offer **{st_.offer.offer_id}** ({st_.offer.name}, {st_.offer.value})"
                                     if st_.offer else " without an offer") + ".")
for n in st_.notes:
    st.info(n)
if st_.offer_decisions:
    st.markdown("#### Why each offer was selected or rejected")
    st.dataframe(safe_df([{"Offer": d.offer_id, "Eligible": "✅" if d.eligible else "❌", "Reasons": "; ".join(d.reasons),
                                "Selected": "⭐" if st_.offer and st_.offer.offer_id == d.offer_id else ""}
                               for d in st_.offer_decisions]), **STRETCH, hide_index=True)
elif st_.objective == "REMIND":
    st.caption("Offers are never evaluated for payment reminders.")
st.markdown("#### Verified facts passed to the writer")
st.json(st_.facts)
st.caption("Only fields allowed by policies/privacy.yaml are shared with the LLM. Policy refs: " + "; ".join(st_.policy_refs))
