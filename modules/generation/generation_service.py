"""Generate -> validate -> classify failure -> repair / retry -> static fallback -> block (Person 3).

Rules (from the build spec):
  DATA / POLICY failure  : stop immediately, no LLM retry (the caller blocks or recomputes).
  FORMAT failure         : one format retry.
  WRITING failure        : targeted repair prompt listing the exact failed checks.
  max repair attempts    : configurable (default 2), then the approved static template.
  static template fails  : BLOCKED and escalated to a human.
The validator is injected so this module never bypasses Person 4's checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from backend.schemas.models import EmailContent, GenerationAttempt, PolicySource, Strategy, ValidationReport
from modules.generation.email_generator import EmailGenerator, TemplateStore
from modules.generation.llm_client import LLMProvider

ValidateFn = Callable[[EmailContent | None], ValidationReport]


@dataclass
class GenerationOutcome:
    content: EmailContent | None
    report: ValidationReport | None
    attempts: list[GenerationAttempt] = field(default_factory=list)
    mode: str = "static"
    model_name: str = "static-template"
    prompt_version: str = "static-template"
    guidance: list[PolicySource] = field(default_factory=list)
    stop_reason: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.report and self.report.passed)


def _format_report(error: str) -> ValidationReport:
    from backend.schemas.models import FailureCategory, ValidationFinding

    f = ValidationFinding(check="SCHEMA", status="FAIL", severity="BLOCK", category=FailureCategory.FORMAT, detail=error)
    return ValidationReport(passed=False, findings=[f], retry_recommended=True, failure_categories=["FORMAT"])


class GenerationService:
    def __init__(self, generator: EmailGenerator, templates: TemplateStore, max_repair_attempts: int = 2):
        self.generator = generator
        self.templates = templates
        self.max_repair_attempts = max_repair_attempts

    def static_draft(self, strategy: Strategy, validate: ValidateFn, attempt_no: int, mode: str) -> tuple[EmailContent, ValidationReport, GenerationAttempt]:
        content = self.templates.render(strategy)
        report = validate(content)
        att = GenerationAttempt(attempt_no=attempt_no, mode=mode, model_name="static-template",
                                prompt_version=f"template:{strategy.template_id}", passed=report.passed,
                                failure_categories=report.failure_categories)
        return content, report, att

    def generate(self, strategy: Strategy, provider: LLMProvider, validate: ValidateFn,
                 guidance: list[PolicySource] | None = None, feedback: str | None = None) -> GenerationOutcome:
        guidance = guidance or []
        out = GenerationOutcome(content=None, report=None, guidance=guidance)

        if not provider.available:  # offline mode: approved static template only
            content, report, att = self.static_draft(strategy, validate, 1, "static")
            out.content, out.report, out.attempts = content, report, [att]
            out.mode = "static"
            out.stop_reason = None if report.passed else "STATIC_TEMPLATE_FAILED_VALIDATION"
            return out

        guidance_text = "\n\n".join(f"[{g.doc_name} - {g.section}]\n{g.excerpt}" for g in guidance)
        out.model_name = provider.model
        draft, version = self.generator.generate(provider, strategy, guidance_text, feedback)
        out.prompt_version = version
        content, report = draft.content, (validate(draft.content) if draft.content else _format_report(draft.error or "no content"))
        out.attempts.append(self._attempt(1, "reviewer_regenerate" if feedback else "llm", provider, version, draft, report))
        repairs, format_retries = 0, 0

        while not report.passed:
            cats = set(report.failure_categories)
            if cats & {"DATA", "POLICY"}:
                out.stop_reason = f"{'/'.join(sorted(cats & {'DATA', 'POLICY'}))} failure - no LLM retry"
                out.content, out.report, out.mode = content, report, "llm"
                return out
            if repairs >= self.max_repair_attempts:
                break
            repairs += 1
            if cats == {"FORMAT"} and content is None:
                if format_retries >= 1:
                    break
                format_retries += 1
                draft, version = self.generator.generate(provider, strategy, guidance_text, feedback)
                mode = "format_retry"
            else:
                failures = [f"{f.check}: {f.detail}" for f in report.blocking_failures]
                draft, version = self.generator.repair(provider, strategy, content, failures)
                mode = "repair"
            content = draft.content
            report = validate(content) if content else _format_report(draft.error or "no content")
            out.attempts.append(self._attempt(len(out.attempts) + 1, mode, provider, version, draft, report))

        if report.passed:
            out.content, out.report, out.mode = content, report, out.attempts[-1].mode
            return out

        # Repairs exhausted (or format retry failed): approved static template with verified facts
        content, report, att = self.static_draft(strategy, validate, len(out.attempts) + 1, "static_fallback")
        out.attempts.append(att)
        out.content, out.report, out.mode = content, report, "static_fallback"
        if not report.passed:
            out.stop_reason = "STATIC_FALLBACK_FAILED_VALIDATION"
        return out

    @staticmethod
    def _attempt(no: int, mode: str, provider: LLMProvider, version: str, draft, report: ValidationReport) -> GenerationAttempt:
        resp = draft.response
        return GenerationAttempt(attempt_no=no, mode=mode, model_name=provider.model, prompt_version=version,
                                 latency_ms=resp.latency_ms if resp else 0, input_tokens=resp.input_tokens if resp else 0,
                                 output_tokens=resp.output_tokens if resp else 0, passed=report.passed,
                                 failure_categories=report.failure_categories, error=draft.error)
