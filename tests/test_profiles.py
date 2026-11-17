from modules.profile_builder.profile_builder import build_profile, profile_to_public_dict


def test_profile_derived_fields(container):
    p = container.engagement.profile("DEMO-D-OVERDUE")
    assert p.days_overdue == 20 and p.payment_status == "UNPAID" and p.amount_due == 134.40
    assert p.days_since_active == 10 and p.first_name == "Vikram"
    assert not p.data_issues


def test_profile_json_is_standardised_and_has_no_protected_fields(container):
    d = profile_to_public_dict(container.engagement.profile("DEMO-A-LOYAL"))
    for key in ("customer_id", "tenure_months", "monthly_charges", "usage_last_3m", "usage_prev_3m", "payment_status",
                "amount_due", "marketing_consent", "churn_status", "customer_service_calls", "on_time_payment_ratio"):
        assert key in d
    assert not {"gender", "age", "senior_citizen", "SeniorCitizen"} & set(d)


def test_contradictory_payment_is_flagged(container):
    p = container.engagement.profile("DEMO-H-CONTRADICTORY")
    assert "CONTRADICTORY_PAYMENT" in [i.code for i in p.data_issues] and p.has_blocking_issue


def test_missing_evidence_is_flagged(container):
    codes = [i.code for i in container.engagement.profile("DEMO-J-MISSING").data_issues]
    assert {"MISSING_TENURE", "MISSING_ACTIVITY", "MISSING_USAGE"} <= set(codes)


def test_unverified_consent_is_a_warning(settings):
    row = {"customer_id": "X", "tenure_months": 5, "payment_status": "PAID", "amount_due": 0, "marketing_consent": None,
           "last_active_date": "2026-11-01", "usage_last_3m": 1, "usage_prev_3m": 1, "on_time_payment_ratio": 1}
    p = build_profile(row, settings)
    issue = [i for i in p.data_issues if i.code == "UNVERIFIED_CONSENT"][0]
    assert issue.severity == "WARN" and p.marketing_consent is None
