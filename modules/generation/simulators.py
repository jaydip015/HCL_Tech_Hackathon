"""Clearly-labelled LLM simulators for offline testing, evaluation and demos (Person 3).

* OfflineSimulatorProvider ("offline-simulator"): behaves like a well-behaved LLM by returning
  the approved template (with placeholders) as JSON. Used when LLM_PROVIDER=offline_simulator
  and by tests. It is never presented as a real model: its model name says "simulator".
* FaultInjectingProvider: wraps any provider and corrupts the first N replies (wrong amount,
  banned phrase, invalid JSON, promo in reminder ...) to demonstrate the validator and repair loop.
"""
from __future__ import annotations

import json
import re

from backend.schemas.models import Offer, Strategy
from modules.generation.email_generator import TemplateStore
from modules.generation.llm_client import LLMProvider, LLMResponse

_TEMPLATE_HINT = re.compile(r"Template hint:\s*([A-Z0-9_]+)")
_HAS_OFFER = re.compile(r"Approved offer attached:\s*yes")


class OfflineSimulatorProvider(LLMProvider):
    name = "offline_simulator"
    model = "offline-simulator (not a real LLM)"
    available = True

    def __init__(self, templates: TemplateStore):
        self.templates = templates

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        hint = _TEMPLATE_HINT.search(user)
        template_id = hint.group(1) if hint else "TPL_THANKS"
        has_offer = bool(_HAS_OFFER.search(user)) or "{offer_value}" in user
        dummy_offer = Offer(offer_id="X", name="x", value="x", terms="x", eligible_segments=[],
                            start_date="2000-01-01", expiry_date="2100-01-01") if has_offer else None
        st = Strategy(customer_id="sim", primary_segment=None, template_id=template_id, offer=dummy_offer)
        content = self.templates.placeholder_content(st)
        text = json.dumps(content.model_dump())
        return LLMResponse(text=text, model=self.model, input_tokens=len(system + user) // 4,
                           output_tokens=len(text) // 4, latency_ms=5)


FAULTS = {
    "wrong_amount": "LLM types its own (wrong) amount instead of the verified one",
    "banned_phrase": "LLM adds a threatening phrase",
    "promo_in_reminder": "LLM adds a discount to a payment reminder",
    "invalid_json": "LLM returns text that is not valid JSON",
    "missing_dispute": "LLM drops the dispute link",
    "invented_offer": "LLM invents an unapproved discount",
}


class FaultInjectingProvider(LLMProvider):
    name = "fault_injection"
    available = True

    def __init__(self, base: LLMProvider, fault: str, times: int = 1):
        if fault not in FAULTS:
            raise ValueError(f"Unknown fault {fault}; choose from {list(FAULTS)}")
        self.base, self.fault, self.remaining = base, fault, times
        self.model = f"{base.model} + injected fault '{fault}'"

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        resp = self.base.complete(system, user, temperature, max_tokens)
        if self.remaining <= 0:
            return resp
        self.remaining -= 1
        if self.fault == "invalid_json":
            resp.text = "Sure! Here is your email: Dear customer, please pay."
            return resp
        try:
            data = json.loads(resp.text[resp.text.find("{"): resp.text.rfind("}") + 1])
        except ValueError:
            return resp
        body = data.get("body", "")
        if self.fault == "wrong_amount":
            if "{amount_due}" in body:
                body = body.replace("{amount_due}", "$1,500.00", 1)
            else:
                body = re.sub(r"\$\d[\d,]*(?:\.\d{2})?", "$1,500.00", body, count=1)
        elif self.fault == "banned_phrase":
            body += "\n\nThis is your final warning before legal action."
        elif self.fault == "promo_in_reminder":
            body += "\n\nPay today and enjoy a 50% discount on next month!"
        elif self.fault == "missing_dispute":
            body = body.replace("{dispute_url}", "our website")
        elif self.fault == "invented_offer":
            body += "\n\nAs a bonus, enjoy 30% off your next three bills."
        data["body"] = body
        resp.text = json.dumps(data)
        return resp
