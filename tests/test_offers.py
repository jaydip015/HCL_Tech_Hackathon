from modules.offers.offer_eligibility import check_offer


def _ctx(container, cid):
    p, seg = container.engagement.classify(cid, persist=False)
    return p, seg


def test_catalog_loaded(container):
    ids = [o.offer_id for o in container.offers.all()]
    assert {"LOYALTY_001", "LOYALTY_2025", "REENGAGE_001", "WINBACK_001", "THANKS_001"} <= set(ids)


def test_loyal_customer_gets_loyalty_offer(container):
    p, seg = _ctx(container, "DEMO-A-LOYAL")
    d = check_offer(container.offers.get("LOYALTY_001"), p, seg, container.settings.as_of_date, container.offers.rules)
    assert d.eligible


def test_expired_offer_rejected(container):
    p, seg = _ctx(container, "DEMO-A-LOYAL")
    d = check_offer(container.offers.get("LOYALTY_2025"), p, seg, container.settings.as_of_date, container.offers.rules)
    assert not d.eligible and any(r.startswith("EXPIRED") for r in d.reasons)


def test_segment_tenure_channel_rules(container):
    p, seg = _ctx(container, "DEMO-B-DECLINING")
    rules, as_of = container.offers.rules, container.settings.as_of_date
    loyalty = check_offer(container.offers.get("LOYALTY_001"), p, seg, as_of, rules)
    assert not loyalty.eligible and any("SEGMENT_NOT_ELIGIBLE" in r for r in loyalty.reasons)
    assert any("TENURE_TOO_LOW" in r for r in loyalty.reasons)
    sms = check_offer(container.offers.get("SMS_ONLY_001"), *_ctx(container, "DEMO-K-CONSISTENT"), as_of, rules)
    assert any("CHANNEL_NOT_ALLOWED" in r for r in sms.reasons)


def test_no_consent_and_overdue_never_eligible(container):
    rules, as_of = container.offers.rules, container.settings.as_of_date
    d = check_offer(container.offers.get("LOYALTY_001"), *_ctx(container, "DEMO-E-NOCONSENT"), as_of, rules)
    assert any("NO_CONSENT" in r for r in d.reasons)
    p, seg = _ctx(container, "DEMO-D-OVERDUE")  # also LOYAL as secondary segment
    for o in container.offers.all():
        assert not check_offer(o, p, seg, as_of, rules).eligible
