from datetime import timedelta

import pytest

from modules.strategy.strategy_selector import reminder_stage_for


@pytest.mark.parametrize("days,stage", [(1, 1), (15, 1), (16, 2), (30, 2), (31, 3), (200, 3)])
def test_reminder_stage_boundaries(settings, days, stage):
    assert reminder_stage_for(days, settings.reminders["stages"])["stage"] == stage


def test_zero_days_has_no_stage(settings):
    assert reminder_stage_for(0, settings.reminders["stages"]) is None


@pytest.mark.parametrize("cid,objective,tone,template,offer", [
    ("DEMO-A-LOYAL", "REWARD", "WARM", "TPL_LOYALTY", "LOYALTY_001"),
    ("DEMO-K-CONSISTENT", "APPRECIATION", "WARM", "TPL_THANKS", "THANKS_001"),
    ("DEMO-B-DECLINING", "REENGAGE", "FRIENDLY", "TPL_REENGAGE", "REENGAGE_001"),
    ("DEMO-C-DORMANT", "REACTIVATE", "FRIENDLY", "TPL_REACTIVATE", "WINBACK_001"),
    ("DEMO-D-OVERDUE", "REMIND", "FIRM", "TPL_REMIND_S2", None),
    ("DEMO-D1-OVERDUE-S1", "REMIND", "COURTEOUS", "TPL_REMIND_S1", None),
    ("DEMO-D3-OVERDUE-S3", "REMIND", "FORMAL", "TPL_REMIND_S3", None),
])
def test_strategy_mapping(container, cid, objective, tone, template, offer):
    _, _, st, _ = container.engagement.decide(cid)
    assert not st.blocked
    assert (st.objective, st.tone, st.template_id) == (objective, tone, template)
    assert (st.offer.offer_id if st.offer else None) == offer


def test_overdue_never_gets_offer_and_has_reminder_facts(container):
    _, _, st, _ = container.engagement.decide("DEMO-D-OVERDUE")
    assert st.offer is None and not st.is_marketing and st.offer_decisions == []
    assert st.facts["amount_due"] == "$134.40" and st.facts["days_overdue"] == 20


def test_no_consent_blocks_marketing(container):
    _, _, st, _ = container.engagement.decide("DEMO-E-NOCONSENT")
    assert st.blocked and [b.code for b in st.block_reasons] == ["NO_CONSENT"] and st.offer is None


def test_recent_contact_blocks(container):
    _, _, st, _ = container.engagement.decide("DEMO-I-RECENT-CONTACT")
    assert st.blocked and "RECENT_CONTACT" in [b.code for b in st.block_reasons]


def test_contradictory_data_escalates(container):
    _, _, st, _ = container.engagement.decide("DEMO-H-CONTRADICTORY")
    assert st.blocked and st.block_reasons[0].category.value == "DATA"


def test_forced_expired_offer_is_recomputed(container):
    _, _, st, _ = container.engagement.decide("DEMO-F-EXPIRED-OFFER", forced_offer_id="LOYALTY_2025")
    assert st.offer.offer_id == "LOYALTY_001"
    assert any("LOYALTY_2025 rejected" in n and "EXPIRED" in n for n in st.notes)


def test_loyal_without_eligible_offer_falls_back_to_appreciation(container):
    p, seg = container.engagement.classify("DEMO-A-LOYAL")
    for o in container.offers._offers:
        if o.offer_id == "LOYALTY_001":
            o.expiry_date = container.settings.as_of_date - timedelta(days=1)
    st = container.selector.select(p, seg, [])
    assert st.objective == "APPRECIATION" and st.offer is None and "fell back" in " ".join(st.notes)


def test_facts_respect_privacy_allow_list(container):
    _, _, st, _ = container.engagement.decide("DEMO-A-LOYAL")
    allowed = set(container.settings.privacy["llm_context_allowed_fields"])
    assert set(st.facts) <= allowed and "email_address" not in st.facts and "customer_name" not in st.facts
