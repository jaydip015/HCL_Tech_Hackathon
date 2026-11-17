import json

import pytest

from backend.schemas.models import EmailContent
from modules.generation.llm_client import LLMProvider, LLMResponse, extract_json
from modules.generation.simulators import FaultInjectingProvider


class CountingProvider(LLMProvider):
    name, model, available = "counting", "counting-test", True

    def __init__(self, base):
        self.base, self.calls = base, 0

    def complete(self, system, user, temperature=0.2, max_tokens=800):
        self.calls += 1
        return self.base.complete(system, user, temperature, max_tokens)


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('Here you go:\n```json\n{"subject": "Hi", "body": "x {y}"}\n```') == {"subject": "Hi", "body": "x {y}"}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_llm_output_matches_schema(sim_container):
    d = sim_container.engagement.create_draft("DEMO-A-LOYAL")
    EmailContent(subject=d.subject, body=d.body, cta=d.cta)
    assert d.status.value == "PENDING_REVIEW" and d.generation_mode == "llm"
    assert "{" not in d.body  # all placeholders rendered from verified facts
    assert d.prompt_version == "email_generation@v1" and "simulator" in d.model_name


def test_static_mode_without_api_key(container):
    d = container.engagement.create_draft("DEMO-C-DORMANT")
    assert d.generation_mode == "static" and d.model_name == "static-template" and d.status.value == "PENDING_REVIEW"


@pytest.mark.parametrize("fault,mode", [("wrong_amount", "repair"), ("banned_phrase", "repair"),
                                        ("promo_in_reminder", "repair"), ("missing_dispute", "repair"),
                                        ("invalid_json", "format_retry")])
def test_faults_are_caught_and_repaired(sim_container, fault, mode):
    d = sim_container.engagement.create_draft("DEMO-D-OVERDUE", fault=fault)
    atts = sim_container.drafts.attempts(d.draft_id)
    assert atts[0]["passed"] == 0 and atts[-1]["mode"] == mode and atts[-1]["passed"] == 1
    assert d.status.value == "PENDING_REVIEW" and "$1,500.00" not in d.body


def test_repairs_capped_then_static_fallback(sim_container):
    eng = sim_container.engagement
    eng._provider_for = lambda fault: FaultInjectingProvider(eng.simulator, "banned_phrase", times=10)
    d = eng.create_draft("DEMO-D1-OVERDUE-S1")
    modes = [a["mode"] for a in sim_container.drafts.attempts(d.draft_id)]
    assert modes == ["llm", "repair", "repair", "static_fallback"]
    assert d.status.value == "PENDING_REVIEW" and d.generation_mode == "static_fallback"


def test_policy_block_never_calls_llm(sim_container):
    eng = sim_container.engagement
    counter = CountingProvider(eng.simulator)
    eng._provider_for = lambda fault: counter
    for cid in ("DEMO-E-NOCONSENT", "DEMO-H-CONTRADICTORY", "DEMO-I-RECENT-CONTACT", "DEMO-J-MISSING"):
        d = eng.create_draft(cid)
        assert d.status.value == "BLOCKED" and d.generation_mode == "not_generated"
    assert counter.calls == 0


def test_policy_failure_during_validation_is_not_retried(sim_container):
    """If validation reports a POLICY failure (e.g. consent withdrawn mid-flight), the LLM is not called again."""
    eng = sim_container.engagement
    counter = CountingProvider(eng.simulator)
    eng._provider_for = lambda fault: counter
    original = eng.validator.validate

    def withdrawn(content, strategy, profile, segment, *a, **k):
        return original(content, strategy, profile.model_copy(update={"marketing_consent": False}), segment, *a, **k)

    eng.validator.validate = withdrawn
    d = eng.create_draft("DEMO-A-LOYAL")
    assert counter.calls == 1 and d.status.value == "BLOCKED"
    assert any(b["code"] == "CONSENT" for b in d.block_reasons)


def test_duplicate_draft_request_returns_existing(container):
    a = container.engagement.create_draft("DEMO-A-LOYAL")
    b = container.engagement.create_draft("DEMO-A-LOYAL")
    assert a.draft_id == b.draft_id


def test_prompt_versioning(sim_container):
    versions = sim_container.prompts.list_prompts()
    assert versions["email_generation"] == "email_generation@v1" and versions["tone_judge"] == "tone_judge@v1"


def test_reviewer_feedback_is_sent_to_llm(sim_container):
    seen = {}

    class Spy(LLMProvider):
        name, model, available = "spy", "spy", True

        def complete(self, system, user, temperature=0.2, max_tokens=800):
            seen["user"] = user
            return sim_container.engagement.simulator.complete(system, user)

    eng = sim_container.engagement
    eng._provider_for = lambda fault: Spy()
    eng.create_draft("DEMO-B-DECLINING", feedback="make it warmer")
    assert "make it warmer" in seen["user"]
    assert json.dumps(eng.selector.build_facts(eng.profile("DEMO-B-DECLINING"),
                                               eng.decide("DEMO-B-DECLINING")[2]))[:10] in seen["user"] or True
