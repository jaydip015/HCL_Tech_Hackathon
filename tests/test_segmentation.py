import pytest

from modules.segmentation.segmentation_engine import SegmentationEngine


def test_demo_labels_classified_correctly(container):
    for cid, lab in container.labels.items():
        _, seg = container.engagement.classify(cid)
        predicted = seg.primary_segment if seg.status == "CLASSIFIED" else None
        assert predicted == lab["expected_segment"], cid


def test_segmentation_is_deterministic(container):
    p = container.engagement.profile("DEMO-D-OVERDUE")
    a = container.segmentation.classify(p).model_dump()
    b = container.segmentation.classify(p).model_dump()
    assert a == b


def test_all_matching_segments_and_reason_codes_kept(container):
    _, seg = container.engagement.classify("DEMO-D-OVERDUE")
    assert seg.segments == ["OVERDUE", "LOYAL"] and seg.secondary_segments == ["LOYAL"]
    assert seg.reason_codes == ["OVERDUE_GT_0D", "TENURE_GE_36M"]
    ev = [e for e in seg.evidence if e.segment == "OVERDUE"][0]
    assert ev.actual == 20 and ev.passed and ev.policy_ref.startswith("Customer Segmentation Policy")


def test_declining_reason_code(container):
    _, seg = container.engagement.classify("DEMO-B-DECLINING")
    assert "USAGE_DROP_GT_40PCT" in seg.reason_codes and seg.confidence == 1.0


@pytest.mark.parametrize("cid", ["DEMO-H-CONTRADICTORY", "DEMO-J-MISSING"])
def test_bad_data_goes_to_manual_review(container, cid):
    _, seg = container.engagement.classify(cid)
    assert seg.status == "MANUAL_REVIEW" and seg.primary_segment is None and seg.manual_review_reasons


def test_churn_label_never_changes_segment(container):
    p = container.engagement.profile("DEMO-A-LOYAL")
    a = container.segmentation.classify(p)
    p2 = p.model_copy(update={"churn_status": 1 - (p.churn_status or 0)})
    b = container.segmentation.classify(p2)
    assert (a.segments, a.primary_segment) == (b.segments, b.primary_segment)


def test_no_rule_match_goes_to_manual_review(container):
    p = container.engagement.profile("DEMO-K-CONSISTENT").model_copy(
        update={"tenure_months": 10, "on_time_payment_ratio": 0.8, "days_since_active": 40})
    seg = container.segmentation.classify(p)
    assert seg.status == "MANUAL_REVIEW" and "NO_RULE_MATCHED" in seg.manual_review_reasons[0]


def test_near_threshold_lowers_confidence(settings, container):
    p = container.engagement.profile("DEMO-A-LOYAL").model_copy(update={"tenure_months": 37})
    seg = SegmentationEngine(settings).classify(p)
    assert seg.primary_segment == "LOYAL" and seg.confidence < 1.0
