import pytest

from backend.schemas.models import EmailContent, Strategy


def _render(c, cid, **strategy_updates):
    profile, seg, st, history = c.engagement.decide(cid)
    if strategy_updates:
        st = Strategy(**{**st.model_dump(), **strategy_updates})
    return profile, seg, st, history, c.templates.render(st)


def _validate(c, profile, seg, st, history, content):
    return c.validator.validate(content, st, profile, seg, history)


def _failed(report):
    return {f.check for f in report.blocking_failures}


@pytest.mark.parametrize("cid", ["DEMO-A-LOYAL", "DEMO-B-DECLINING", "DEMO-C-DORMANT", "DEMO-D-OVERDUE",
                                 "DEMO-D1-OVERDUE-S1", "DEMO-D3-OVERDUE-S3", "DEMO-K-CONSISTENT"])
def test_approved_templates_pass(container, cid):
    p, s, st, h, content = _render(container, cid)
    rep = _validate(container, p, s, st, h, content)
    assert rep.passed, [(f.check, f.detail) for f in rep.blocking_failures]


def test_invalid_amount_caught(container):
    p, s, st, h, content = _render(container, "DEMO-D-OVERDUE")
    bad = EmailContent(subject=content.subject, body=content.body.replace("$134.40", "$1,500.00"), cta=content.cta)
    rep = _validate(container, p, s, st, h, bad)
    assert not rep.passed and "AMOUNT_VERIFICATION" in _failed(rep) and rep.retry_recommended


def test_wrong_date_caught(container):
    p, s, st, h, content = _render(container, "DEMO-D-OVERDUE")
    bad = EmailContent(subject=content.subject, body=content.body.replace("28 October 2026", "2 November 2026"), cta="")
    assert "DATE_VERIFICATION" in _failed(_validate(container, p, s, st, h, bad))


def test_expired_offer_caught(container):
    expired = container.offers.get("LOYALTY_2025")
    p, s, st, h, content = _render(container, "DEMO-A-LOYAL", offer=expired)
    st.facts = container.selector.build_facts(p, st)
    content = container.templates.render(st)
    rep = _validate(container, p, s, st, h, content)
    assert "OFFER_EXPIRY" in _failed(rep) and "POLICY" in rep.failure_categories and not rep.retry_recommended


def test_unapproved_offer_value_caught(container):
    p, s, st, h, content = _render(container, "DEMO-A-LOYAL")
    bad = EmailContent(subject=content.subject, body=content.body.replace("10% discount", "25% discount"), cta="")
    assert {"PERCENTAGE_VERIFICATION", "OFFER_TERMS"} <= _failed(_validate(container, p, s, st, h, bad))


def test_missing_consent_blocks_promotional_message(container):
    p, s, st, h, content = _render(container, "DEMO-A-LOYAL")
    p2 = p.model_copy(update={"marketing_consent": False})
    rep = _validate(container, p2, s, st, h, content)
    assert "CONSENT" in _failed(rep) and not rep.retry_recommended


def test_overdue_customer_never_receives_promotion(container):
    p, s, st, h, content = _render(container, "DEMO-D-OVERDUE")
    bad = EmailContent(subject=content.subject, body=content.body + "\nEnjoy a special offer with cashback!", cta="")
    assert "NO_PROMO_IN_REMINDER" in _failed(_validate(container, p, s, st, h, bad))


def test_recent_contact_blocks_outreach(container):
    p, s, st, h, content = _render(container, "DEMO-A-LOYAL")
    p2 = p.model_copy(update={"last_contacted_date": container.settings.as_of_date})
    assert "FREQUENCY" in _failed(_validate(container, p2, s, st, h, content))


def test_stage_mismatch_caught(container):
    p, s, st, h, content = _render(container, "DEMO-D-OVERDUE", reminder_stage=1)
    assert "OVERDUE_STAGE" in _failed(_validate(container, p, s, st, h, content))


@pytest.mark.parametrize("extra,check", [
    ("Your card 4111 1111 1111 1111 is on file.", "PII_LEAKAGE"),
    ("Email ravi.other@gmail.com for help.", "PII_LEAKAGE"),
    ("Pay here: http://totally-legit-pay.biz", "PII_LEAKAGE"),
    ("This is your final warning.", "PROHIBITED_PHRASES"),
    ("You are in our DORMANT segment.", "INTERNAL_DISCLOSURE"),
    ("Your plan {plan_name} renews soon.", "PLACEHOLDERS_RESOLVED"),
    ("You have been with us for 99 months.", "UNSUPPORTED_CLAIMS"),
])
def test_writing_failures(container, extra, check):
    p, s, st, h, content = _render(container, "DEMO-C-DORMANT")
    bad = EmailContent(subject=content.subject, body=content.body + "\n" + extra, cta=content.cta)
    rep = _validate(container, p, s, st, h, bad)
    assert check in _failed(rep) and rep.retry_recommended


def test_required_dispute_contact(container):
    p, s, st, h, content = _render(container, "DEMO-D-OVERDUE")
    bad = EmailContent(subject=content.subject, body=content.body.replace(st.facts["dispute_url"], "our site"), cta="")
    assert "SUPPORT_CONTACT" in _failed(_validate(container, p, s, st, h, bad))


def test_schema_failure_is_format_category(container):
    p, s, st, h, _ = _render(container, "DEMO-A-LOYAL")
    rep = container.validator.validate({"subject": "Hi", "body": "short"}, st, p, s, h)
    assert not rep.passed and rep.failure_categories == ["FORMAT"]


def test_tone_heuristics_warn_only(container):
    p, s, st, h, content = _render(container, "DEMO-C-DORMANT")
    loud = EmailContent(subject=content.subject, body=content.body + "\nAMAZING GREAT SUPER NEWS!!!!", cta="")
    rep = _validate(container, p, s, st, h, loud)
    assert rep.passed and {w.check for w in rep.warnings} >= {"TONE_EXCLAMATIONS", "TONE_ALL_CAPS"}


def test_validation_output_shape(container):
    p, s, st, h, content = _render(container, "DEMO-A-LOYAL")
    rep = _validate(container, p, s, st, h, content).model_dump(mode="json")
    assert set(rep) >= {"passed", "findings", "retry_recommended"}
    assert {"check", "status", "detail"} <= set(rep["findings"][0])
    assert len({f["check"] for f in rep["findings"]}) >= 16
