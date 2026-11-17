"""Tone validation (Person 4).

Deterministic heuristics run on every draft. The optional LLM judge (a smaller model, a
fixed rubric, temperature 0) adds ADVISORY scores only: low scores create WARN findings for
the reviewer and can never approve, block or send anything on their own.
"""
from __future__ import annotations

import re
from typing import Any

from backend.schemas.models import EmailContent, FailureCategory, Strategy, ValidationFinding
from modules.generation.llm_client import LLMError, LLMProvider, extract_json
from modules.generation.prompt_manager import PromptManager
from modules.validation.context import ValidationContext, contains_term, finding, warn


def run(ctx: ValidationContext) -> list[ValidationFinding]:
    out: list[ValidationFinding] = []
    text = ctx.full_text
    rules = ctx.comm.get("tone_rules", {})

    banned = [p for p in ctx.comm.get("banned_phrases", []) if p.lower() in text.lower()]
    out.append(finding("PROHIBITED_PHRASES", not banned, f"Prohibited phrase(s): {banned}.", FailureCategory.WRITING,
                       "No prohibited phrases."))
    internal = [t for t in ctx.comm.get("internal_terms", []) if contains_term(text, t)]
    out.append(finding("INTERNAL_DISCLOSURE", not internal,
                       f"Internal labels disclosed to the customer: {internal}.", FailureCategory.WRITING,
                       "No internal segmentation labels disclosed."))

    tone = (ctx.strategy.tone or "").upper()
    req = (rules.get(tone) or {}).get("required_any", [])
    if req and not any(w.lower() in text.lower() for w in req):
        out.append(warn("TONE_MATCH", f"Required {tone} tone markers missing (expected one of {req})."))
    else:
        out.append(finding("TONE_MATCH", True, "", None, f"{tone or 'Default'} tone markers present."))
    excl = text.count("!")
    if excl > int(rules.get("max_exclamations", 3)):
        out.append(warn("TONE_EXCLAMATIONS", f"{excl} exclamation marks (max {rules.get('max_exclamations', 3)})."))
    caps = [w for w in re.findall(r"\b[A-Z]{4,}\b", text) if w not in {"USD", "EMAIL"}]
    if len(caps) > int(rules.get("max_all_caps_words", 2)):
        out.append(warn("TONE_ALL_CAPS", f"Shouting detected: {caps[:5]}."))
    return out


def judge(provider: LLMProvider, prompts: PromptManager, content: EmailContent, strategy: Strategy,
          warn_below: int = 3) -> tuple[dict[str, Any] | None, list[ValidationFinding]]:
    """Advisory LLM-as-judge. Returns (scores, WARN findings). Never raises."""
    if not provider.available:
        return None, []
    p = prompts.render("tone_judge", tone=strategy.tone, objective=strategy.objective, subject=content.subject,
                       body=content.body)
    try:
        resp = provider.complete(p.system, p.user, temperature=0.0, max_tokens=300)
        data = extract_json(resp.text)
        scores = {k: int(data[k]) for k in ("respectfulness", "clarity", "tone_match", "pressure_tactics")}
    except (LLMError, ValueError, KeyError, TypeError) as exc:
        return {"error": str(exc)[:200]}, [warn("TONE_JUDGE", f"Tone judge unavailable: {str(exc)[:120]}", None)]
    scores["issues"] = data.get("issues", [])
    scores["model"] = resp.model
    scores["prompt_version"] = p.version
    low = {k: v for k, v in scores.items() if k in ("respectfulness", "clarity", "tone_match", "pressure_tactics")
           and v < warn_below}
    findings = [warn("TONE_JUDGE", f"Advisory tone scores below {warn_below}: {low}. Issues: {scores['issues']}")] if low else \
        [ValidationFinding(check="TONE_JUDGE", status="PASS", severity="INFO", detail=f"Advisory scores: {scores}")]
    return scores, findings
