"""API tests. With FastAPI installed they use TestClient against the real app; otherwise the
route functions are executed directly through a minimal fake `fastapi` module."""
import importlib
import sys

import pytest

from tests.fakes import make_fake_fastapi

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient  # noqa: F401
    REAL_FASTAPI = True
except Exception:  # noqa: BLE001
    REAL_FASTAPI = False


@pytest.fixture
def api(container, monkeypatch):
    if not REAL_FASTAPI:
        monkeypatch.setitem(sys.modules, "fastapi", make_fake_fastapi())
    for m in [m for m in list(sys.modules) if m.startswith("backend.api") or m == "main"]:
        sys.modules.pop(m)
    import backend.services.container as cont
    monkeypatch.setattr(cont, "get_container", lambda: container)
    deps = importlib.import_module("backend.api.deps")
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return container


@pytest.mark.skipif(not REAL_FASTAPI, reason="FastAPI not installed")
def test_api_with_testclient(api):
    from fastapi.testclient import TestClient

    import main
    client = TestClient(main.app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/customers", params={"source": "demo"}).json()["total"] == 13
    assert client.get("/customers/NOPE").status_code == 404
    ov = client.get("/customers/DEMO-A-LOYAL/overview").json()
    assert ov["primary_segment"] == "LOYAL" and ov["segment_checks"][3]["policy"]["ref"].endswith("§2.4")
    assert client.get("/customers/NOPE/overview").status_code == 404
    r = client.post("/customers/DEMO-A-LOYAL/draft", json={})
    assert r.status_code == 201
    draft_id = r.json()["draft"]["draft_id"]
    assert client.post(f"/send/{draft_id}", json={"reviewer": "a"}).status_code == 409
    assert client.post(f"/review/{draft_id}/approve", json={"reviewer": "a"}).status_code == 200
    assert client.post(f"/send/{draft_id}", json={"reviewer": "a"}).json()["status"] == "MOCK_SENT"
    assert client.post(f"/send/{draft_id}", json={"reviewer": "a"}).status_code == 409
    q = client.post("/customers/DEMO-E-NOCONSENT/policy-query", json={"question": "Why was a promotional email blocked?"})
    assert "NO_CONSENT" in q.json()["answer"]
    assert client.get(f"/audit/{draft_id}").json()["record"]["send_status"] == "MOCK_SENT"
    assert client.get("/metrics").json()["mock_emails_sent"] == 1


@pytest.mark.skipif(REAL_FASTAPI, reason="covered by the TestClient test")
def test_route_functions_directly(api):
    from backend.api import customer_routes, generation_routes, policy_routes, review_routes
    from tests.fakes import HTTPException

    c = api
    assert customer_routes.list_customers(q=None, segment=None, source="demo", limit=50, offset=0, c=c)["total"] == 13
    assert customer_routes.get_customer("DEMO-A-LOYAL", c=c)["tenure_months"] == 48
    with pytest.raises(HTTPException) as e:
        customer_routes.get_customer("NOPE", c=c)
    assert e.value.status_code == 404
    assert customer_routes.classify("DEMO-B-DECLINING", c=c)["primary_segment"] == "DECLINING"
    assert generation_routes.offers(c=c)["catalog_version"] == "offers-2026.11"
    s = generation_routes.strategy("DEMO-F-EXPIRED-OFFER", generation_routes.StrategyRequest(forced_offer_id="LOYALTY_2025"), c=c)
    assert s["strategy"]["offer"]["offer_id"] == "LOYALTY_001"
    r = generation_routes.create_draft("DEMO-A-LOYAL", generation_routes.DraftRequest(), c=c)
    did = r["draft"]["draft_id"]
    assert r["validation"]["passed"]
    with pytest.raises(HTTPException) as e:
        review_routes.send(did, review_routes.Reviewer(reviewer="a"), c=c)
    assert e.value.status_code == 409
    assert review_routes.approve(did, review_routes.Reviewer(reviewer="a"), c=c)["status"] == "APPROVED"
    assert review_routes.send(did, review_routes.Reviewer(reviewer="a"), c=c)["status"] == "MOCK_SENT"
    with pytest.raises(HTTPException):
        review_routes.send(did, review_routes.Reviewer(reviewer="a"), c=c)
    assert review_routes.audit(did, c=c)["record"]["send_status"] == "MOCK_SENT"
    assert review_routes.metrics(c=c)["mock_emails_sent"] == 1
    q = policy_routes.policy_query("DEMO-E-NOCONSENT", policy_routes.PolicyQuery(question="Why was a promotional email blocked?"), c=c)
    assert "NO_CONSENT" in q["answer"] and "decision_evidence" not in q
    d2 = generation_routes.create_draft("DEMO-D-OVERDUE", generation_routes.DraftRequest(), c=c)["draft"]["draft_id"]
    ed = review_routes.edit(d2, review_routes.EditBody(reviewer="b", subject="Payment reminder for you",
                                                       body="Please pay $9,999.00 today. Thanks a lot for your help."), c=c)
    assert ed["draft"]["status"] == "NEEDS_FIX" and not ed["validation"]["passed"]
    with pytest.raises(HTTPException) as e:
        review_routes.queue(status=["BOGUS"], limit=10, c=c)
    assert e.value.status_code == 422
    import main
    assert main.health()["status"] == "ok"
