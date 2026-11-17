import pytest

from modules.email.mock_email_service import DeliveryError


def _approved(c, cid):
    d = c.engagement.create_draft(cid)
    c.review.approve(d.draft_id, "alice")
    return d


def test_mock_email_service_works(container):
    d = _approved(container, "DEMO-A-LOYAL")
    res = container.email.send(d.draft_id, "alice")
    assert res["status"] == "MOCK_SENT" and res["to"].startswith("p***@")
    assert container.drafts.get(d.draft_id).status.value == "MOCK_SENT"
    hist = container.drafts.contact_history("DEMO-A-LOYAL")
    assert len(hist) == 1 and hist[0].template_id == "TPL_LOYALTY"


def test_unapproved_draft_cannot_be_sent(container):
    d = container.engagement.create_draft("DEMO-B-DECLINING")
    with pytest.raises(DeliveryError, match="NOT_APPROVED"):
        container.email.send(d.draft_id)


def test_rejected_draft_cannot_be_sent(container):
    d = container.engagement.create_draft("DEMO-B-DECLINING")
    container.review.reject(d.draft_id, "bob", "nope")
    with pytest.raises(DeliveryError):
        container.email.send(d.draft_id)


def test_failed_validation_cannot_be_sent(container):
    d = container.engagement.create_draft("DEMO-E-NOCONSENT")
    with pytest.raises(DeliveryError):
        container.email.send(d.draft_id)


def test_duplicate_delivery_prevented(container):
    d = _approved(container, "DEMO-K-CONSISTENT")
    container.email.send(d.draft_id)
    with pytest.raises(DeliveryError, match="ALREADY_DELIVERED"):
        container.email.send(d.draft_id)
    assert container.db.scalar("SELECT COUNT(*) FROM mock_deliveries WHERE draft_id = ?", (d.draft_id,)) == 1


def test_customer_paid_before_send_cancels_reminder(container):
    d = _approved(container, "DEMO-D-OVERDUE")
    container.customers.update_fields("DEMO-D-OVERDUE", payment_status="PAID", amount_due=0.0)
    with pytest.raises(DeliveryError, match="already paid"):
        container.email.send(d.draft_id)
    assert container.drafts.get(d.draft_id).status.value == "CANCELLED"


def test_consent_withdrawn_before_send_blocks(container):
    d = _approved(container, "DEMO-C-DORMANT")
    container.customers.update_fields("DEMO-C-DORMANT", marketing_consent=0)
    with pytest.raises(DeliveryError, match="CONSENT"):
        container.email.send(d.draft_id)
    assert container.drafts.get(d.draft_id).status.value == "BLOCKED"


def test_after_send_recent_contact_blocks_next_outreach(container):
    d = _approved(container, "DEMO-A-LOYAL")
    container.email.send(d.draft_id)
    nd = container.engagement.create_draft("DEMO-A-LOYAL")
    codes = [b["code"] for b in nd.block_reasons]
    assert nd.status.value == "BLOCKED" and "RECENT_CONTACT" in codes and "DUPLICATE_OUTREACH" in codes


def test_audit_logs_capture_each_decision(container):
    d = _approved(container, "DEMO-A-LOYAL")
    container.email.send(d.draft_id, "alice")
    events = [e["event"] for e in container.audit.events(draft_id=d.draft_id)]
    assert events[:3] == ["CLASSIFIED", "STRATEGY_SELECTED", "DRAFT_GENERATED"]
    assert "APPROVED" in events and events[-1] == "MOCK_SENT"
    rec = container.audit.trace(d.draft_id)["record"]
    for key in ("draft_id", "customer_id", "segments", "reason_codes", "policy_version", "prompt_version", "model_name",
                "facts_used", "selected_offer", "validation_result", "reviewer_action", "rejection_reason",
                "generation_attempt_count", "token_usage", "latency_ms", "send_status", "timestamp"):
        assert key in rec
    assert rec["send_status"] == "MOCK_SENT" and rec["facts_used"]["first_name"] == "[REDACTED]"
    raw = str(container.db.query("SELECT payload_json FROM audit_logs"))
    assert "Priya" not in raw and "priya.sharma@example.com" not in raw
