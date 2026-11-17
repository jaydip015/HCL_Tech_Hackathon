import pytest

from modules.review.review_service import ReviewError


def test_approve_only_after_passing_validation(container):
    d = container.engagement.create_draft("DEMO-A-LOYAL")
    assert container.review.can_approve(d.draft_id)[0]
    assert container.review.approve(d.draft_id, "alice").status.value == "APPROVED"


def test_blocked_draft_cannot_be_approved(container):
    d = container.engagement.create_draft("DEMO-E-NOCONSENT")
    with pytest.raises(ReviewError):
        container.review.approve(d.draft_id, "alice")


def test_manual_edit_triggers_revalidation(container):
    d = container.engagement.create_draft("DEMO-D-OVERDUE")
    n_before = len(container.db.query("SELECT * FROM validation_reports WHERE draft_id = ?", (d.draft_id,)))
    nd, rep = container.review.edit(d.draft_id, "bob", d.subject, d.body.replace("$134.40", "$13.44"))
    assert not rep.passed and nd.status.value == "NEEDS_FIX"
    assert len(container.db.query("SELECT * FROM validation_reports WHERE draft_id = ?", (d.draft_id,))) == n_before + 1
    with pytest.raises(ReviewError):
        container.review.approve(d.draft_id, "bob")
    nd, rep = container.review.edit(d.draft_id, "bob", d.subject, d.body)  # fix it again
    assert rep.passed and nd.status.value == "PENDING_REVIEW"


def test_edit_of_approved_draft_needs_reapproval(container):
    d = container.engagement.create_draft("DEMO-A-LOYAL")
    container.review.approve(d.draft_id, "alice")
    nd, rep = container.review.edit(d.draft_id, "alice", d.subject, d.body.replace("Dear", "Hello"))
    assert rep.passed and nd.status.value == "PENDING_REVIEW"


def test_reject_requires_reason_and_is_final(container):
    d = container.engagement.create_draft("DEMO-B-DECLINING")
    with pytest.raises(ReviewError):
        container.review.reject(d.draft_id, "bob", "  ")
    container.review.reject(d.draft_id, "bob", "Not relevant")
    with pytest.raises(ReviewError):
        container.review.approve(d.draft_id, "bob")
    with pytest.raises(ReviewError):
        container.review.edit(d.draft_id, "bob", d.subject, d.body)


def test_regenerate_with_feedback(container):
    d = container.engagement.create_draft("DEMO-C-DORMANT")
    with pytest.raises(ReviewError):
        container.review.regenerate(d.draft_id, "bob", "")
    new = container.review.regenerate(d.draft_id, "bob", "Make it shorter")
    assert new.draft_id != d.draft_id and container.drafts.get(d.draft_id).status.value == "CANCELLED"
    assert any(r["action"] == "REGENERATE" for r in container.drafts.reviews(d.draft_id))


def test_blocked_before_generation_cannot_be_edited(container):
    d = container.engagement.create_draft("DEMO-H-CONTRADICTORY")
    with pytest.raises(ReviewError):
        container.review.edit(d.draft_id, "bob", "Hello there", "Please pay your bill of $45.00 now thanks.")
