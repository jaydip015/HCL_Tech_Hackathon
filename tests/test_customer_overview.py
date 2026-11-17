"""Customer overview: category decision + rule checks + quoted policy proof (deterministic)."""
import pytest

from backend.services.engagement_service import NotFoundError


def test_loyal_customer_overview_has_proof(container):
    ov = container.overview.overview("DEMO-A-LOYAL")
    assert ov.status == "CLASSIFIED" and ov.primary_segment == "LOYAL" and "CONSISTENT" in ov.secondary_segments
    assert [s.segment for s in ov.segment_checks] == ["OVERDUE", "DORMANT", "DECLINING", "LOYAL", "CONSISTENT"]
    loyal = next(s for s in ov.segment_checks if s.segment == "LOYAL")
    assert loyal.matched and loyal.is_primary and all(cond.passed for cond in loyal.conditions)
    tenure = loyal.conditions[0]
    assert tenure.reason_code == "TENURE_GE_36M" and tenure.actual == "48" and "meets it" in tenure.explanation
    # The proof is the policy section quoted word for word from the knowledge base.
    assert loyal.policy and loyal.policy.ref == "Customer Segmentation Policy §2.4"
    assert "tenure is 36 months or more" in loyal.policy.text
    dormant = next(s for s in ov.segment_checks if s.segment == "DORMANT")
    assert not dormant.matched and "does not meet" in dormant.conditions[0].explanation
    assert "LOYAL comes first" in ov.headline and ov.priority_policy.ref.endswith("§1")
    assert ov.objective == "REWARD" and ov.offer and not ov.blocked
    assert {q.doc_id for q in ov.strategy_policies} == {"POL-LOYALTY", "POL-OFFERS"}


def test_every_segment_has_a_policy_quote(container):
    for cid in ("DEMO-B-DECLINING", "DEMO-C-DORMANT", "DEMO-D-OVERDUE", "DEMO-K-CONSISTENT"):
        ov = container.overview.overview(cid)
        assert ov.primary_segment and all(s.policy and s.policy.text for s in ov.segment_checks)


def test_overdue_reminder_policy_listed_once(container):
    ov = container.overview.overview("DEMO-D-OVERDUE")
    assert ov.primary_segment == "OVERDUE" and ov.reminder_stage == 2 and ov.offer is None
    refs = [q.ref for q in ov.strategy_policies]
    assert refs == ["Payment Reminder Policy §2 (stage 2)"]


def test_manual_review_and_blocks_cite_policy(container):
    ov = container.overview.overview("DEMO-J-MISSING")
    assert ov.status == "MANUAL_REVIEW" and ov.primary_segment is None and "manual review" in ov.headline
    assert ov.manual_review_reasons and all(r.policy and r.policy.ref == "Customer Segmentation Policy §3"
                                            for r in ov.manual_review_reasons)
    ov = container.overview.overview("DEMO-E-NOCONSENT")
    assert ov.blocked and ov.block_reasons[0].policy.doc_id == "POL-CONSENT"


def test_overview_has_no_personal_data(container):
    dump = container.overview.overview("DEMO-A-LOYAL").model_dump_json()
    row = container.customers.get_row("DEMO-A-LOYAL")
    for key in ("customer_name", "email_address"):
        if row.get(key):
            assert row[key] not in dump


def test_unknown_customer_raises(container):
    with pytest.raises(NotFoundError):
        container.overview.overview("NOPE")
