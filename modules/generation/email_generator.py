"""Email drafting: static templates, LLM prompts, placeholder rendering (Person 3).

Design choice: the LLM writes placeholders such as {amount_due}; code substitutes the
verified values. The validator still checks the final text, so a model that types its own
numbers anyway is caught (see scenario G).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.schemas.models import EmailContent, Strategy
from modules.generation.llm_client import LLMError, LLMProvider, LLMResponse, extract_json
from modules.generation.prompt_manager import PromptManager

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}|\{([a-z_]+)\}")
_OFFER_BLOCK = re.compile(r"\[\[OFFER\]\](.*?)\[\[/OFFER\]\]", re.S)


class TemplateStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def raw(self, template_id: str) -> tuple[str, str, str]:
        text = (self.folder / f"{template_id}.txt").read_text(encoding="utf-8")
        header, body = text.split("---", 1)
        meta = dict(line.split(":", 1) for line in header.strip().splitlines() if ":" in line)
        return meta.get("Subject", "").strip(), meta.get("CTA", "").strip(), body.strip("\n")

    def placeholder_content(self, strategy: Strategy) -> EmailContent:
        """Template with placeholders left in (used by the offline simulator)."""
        subject, cta, body = self.raw(strategy.template_id or "TPL_THANKS")
        body = _OFFER_BLOCK.sub((lambda m: "\n" + m.group(1).strip() + "\n") if strategy.offer else "", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        return EmailContent(subject=subject, body=body, cta=cta)

    def render(self, strategy: Strategy) -> EmailContent:
        return render_placeholders(self.placeholder_content(strategy), strategy.facts)


def render_placeholders(content: EmailContent, facts: dict[str, Any]) -> EmailContent:
    def sub(text: str) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1) or m.group(2)
            return str(facts[key]) if key in facts and facts[key] not in (None, "") else m.group(0)
        return _PLACEHOLDER.sub(repl, text)

    return EmailContent(subject=sub(content.subject)[:120], body=sub(content.body), cta=sub(content.cta)[:200])


def unresolved_placeholders(text: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _PLACEHOLDER.finditer(text)]


def must_include_for(strategy: Strategy, reminder_cfg: dict) -> list[str]:
    if strategy.objective == "REMIND":
        return list(reminder_cfg.get("must_include", []))
    items = ["support_phone"]
    if strategy.offer:
        items += ["offer_value", "offer_terms", "offer_expiry"]
    return items


@dataclass
class LLMDraft:
    content: EmailContent | None
    response: LLMResponse | None
    error: str | None
    raw: str = ""


class EmailGenerator:
    def __init__(self, prompts: PromptManager, templates: TemplateStore, reminder_cfg: dict,
                 temperature: float = 0.2, max_tokens: int = 900):
        self.prompts = prompts
        self.templates = templates
        self.reminder_cfg = reminder_cfg
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _common(self, strategy: Strategy) -> dict[str, Any]:
        return {
            "objective": strategy.objective, "tone": strategy.tone,
            "reminder_stage": strategy.reminder_stage or "n/a", "template_id": strategy.template_id,
            "has_offer": "yes" if strategy.offer else "no (do not mention any offer)",
            "must_include": ", ".join("{" + m + "}" for m in must_include_for(strategy, self.reminder_cfg)),
            "facts_json": json.dumps(strategy.facts, indent=2, ensure_ascii=False),
            "company_name": strategy.facts.get("company_name", ""),
        }

    def _call(self, provider: LLMProvider, system: str, user: str) -> LLMDraft:
        try:
            resp = provider.complete(system, user, temperature=self.temperature, max_tokens=self.max_tokens)
        except LLMError as exc:
            return LLMDraft(None, None, f"LLM_ERROR: {exc}")
        try:
            content = EmailContent(**extract_json(resp.text))
        except (ValueError, ValidationError, TypeError) as exc:
            return LLMDraft(None, resp, f"FORMAT_ERROR: {str(exc)[:300]}", resp.text)
        return LLMDraft(content, resp, None, resp.text)

    def generate(self, provider: LLMProvider, strategy: Strategy, guidance: str, feedback: str | None = None) -> tuple[LLMDraft, str]:
        p = self.prompts.render("email_generation", guidance=guidance or "(none)",
                                feedback=f"Reviewer feedback to apply: {feedback}\n" if feedback else "",
                                **self._common(strategy))
        draft = self._call(provider, p.system, p.user)
        if draft.content:
            draft.content = render_placeholders(draft.content, strategy.facts)
        return draft, p.version

    def repair(self, provider: LLMProvider, strategy: Strategy, previous: EmailContent | None,
               failures: list[str]) -> tuple[LLMDraft, str]:
        prev = previous.model_dump() if previous else {"subject": "", "body": "", "cta": ""}
        p = self.prompts.render("email_repair", failures="\n".join(f"- {f}" for f in failures),
                                previous_json=json.dumps(prev, ensure_ascii=False, indent=2), **self._common(strategy))
        draft = self._call(provider, p.system, p.user)
        if draft.content:
            draft.content = render_placeholders(draft.content, strategy.facts)
        return draft, p.version
