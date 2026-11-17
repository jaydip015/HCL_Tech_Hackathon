"""Integration layer: wires the four modules into the end-to-end pipeline.

profile (P1) -> segmentation (P2) -> strategy + offer (P3) -> RAG guidance (P2)
-> generation with repair/fallback (P3) -> validation (P4) -> draft + audit (P4).
No module can skip another module's rules: every draft passes through the validator, and a
blocked strategy never reaches the LLM.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from backend.schemas.models import (ContactRecord, CustomerProfile, Draft, DraftStatus, SegmentResult, Strategy,
                                    ValidationReport)
from config import Settings
from modules.generation.generation_service import GenerationOutcome, GenerationService
from modules.generation.llm_client import LLMProvider
from modules.generation.prompt_manager import PromptManager
from modules.generation.simulators import FaultInjectingProvider, OfflineSimulatorProvider
from modules.profile_builder.customer_repository import CustomerRepository
from modules.profile_builder.profile_builder import build_profile
from modules.rag.retriever import PolicyRetriever
from modules.review.draft_repository import DraftRepository
from modules.segmentation.segmentation_engine import SegmentationEngine
from modules.strategy.strategy_selector import StrategySelector
from modules.validation import tone_validator
from modules.validation.validator import EmailValidator
from modules.audit.audit_service import AuditService


class NotFoundError(KeyError):
    pass


class EngagementService:
    def __init__(self, settings: Settings, customers: CustomerRepository, segmentation: SegmentationEngine,
                 selector: StrategySelector, retriever: PolicyRetriever | None, generation: GenerationService,
                 provider: LLMProvider, judge_provider: LLMProvider, validator: EmailValidator,
                 drafts: DraftRepository, audit: AuditService, prompts: PromptManager, simulator: OfflineSimulatorProvider):
        self.settings = settings
        self.customers = customers
        self.segmentation = segmentation
        self.selector = selector
        self.retriever = retriever
        self.generation = generation
        self.provider = provider
        self.judge_provider = judge_provider
        self.validator = validator
        self.drafts = drafts
        self.audit = audit
        self.prompts = prompts
        self.simulator = simulator

    # ------------------------------------------------------------ context
    def profile(self, customer_id: str) -> CustomerProfile:
        row = self.customers.get_row(customer_id)
        if row is None:
            raise NotFoundError(f"Customer {customer_id} not found")
        return build_profile(row, self.settings)

    def history(self, customer_id: str) -> list[ContactRecord]:
        return self.drafts.contact_history(customer_id)

    def classify(self, customer_id: str, persist: bool = True) -> tuple[CustomerProfile, SegmentResult]:
        profile = self.profile(customer_id)
        seg = self.segmentation.classify(profile)
        if persist:
            self.customers.save_segment(seg.model_dump(mode="json"))
        return profile, seg

    def decide(self, customer_id: str, forced_offer_id: str | None = None
               ) -> tuple[CustomerProfile, SegmentResult, Strategy, list[ContactRecord]]:
        profile, seg = self.classify(customer_id)
        history = self.history(customer_id)
        strategy = self.selector.select(profile, seg, history, forced_offer_id=forced_offer_id)
        return profile, seg, strategy, history

    def decision_evidence(self, customer_id: str) -> dict[str, Any]:
        """Verified evidence for policy Q&A (only this customer's data, no name/email)."""
        profile, seg, strategy, _ = self.decide(customer_id)
        p = profile.model_dump(mode="json", exclude={"customer_name", "email_address", "field_sources"})
        return {"profile": p, "segment": seg.model_dump(mode="json"),
                "strategy": strategy.model_dump(mode="json", exclude={"facts"})}

    # ------------------------------------------------------------ provider choice
    def _provider_for(self, fault: str | None) -> LLMProvider:
        base = self.provider
        if fault:
            # Fault injection needs an "LLM" reply to corrupt; offline we use the labelled simulator.
            return FaultInjectingProvider(base if base.available else self.simulator, fault)
        return base

    # ------------------------------------------------------------ main entry
    def create_draft(self, customer_id: str, *, forced_offer_id: str | None = None, fault: str | None = None,
                     feedback: str | None = None, actor: str = "system", supersede: bool = False) -> Draft:
        existing = self.drafts.open_draft_for(customer_id)
        if existing and not supersede:
            self.audit.log("DUPLICATE_DRAFT_REQUEST", draft_id=existing.draft_id, customer_id=customer_id, actor=actor,
                           payload={"note": "An open draft already exists; returning it instead of generating another."})
            return existing
        if existing and supersede:
            self.drafts.update_status(existing.draft_id, DraftStatus.CANCELLED)
            self.audit.log("DRAFT_SUPERSEDED", draft_id=existing.draft_id, customer_id=customer_id, actor=actor)

        started = time.perf_counter()
        draft_id = f"DRF-{uuid.uuid4().hex[:10].upper()}"
        profile, seg, strategy, history = self.decide(customer_id, forced_offer_id)
        self.audit.log("CLASSIFIED", draft_id=draft_id, customer_id=customer_id, actor=actor,
                       payload={"status": seg.status, "segments": seg.segments, "reason_codes": seg.reason_codes,
                                "confidence": seg.confidence, "manual_review_reasons": seg.manual_review_reasons,
                                "policy_version": seg.policy_version})
        self.audit.log("STRATEGY_SELECTED", draft_id=draft_id, customer_id=customer_id, actor=actor,
                       payload={"objective": strategy.objective, "tone": strategy.tone, "template": strategy.template_id,
                                "stage": strategy.reminder_stage, "offer": strategy.offer.offer_id if strategy.offer else None,
                                "blocked": strategy.blocked, "block_reasons": [b.model_dump(mode="json") for b in strategy.block_reasons],
                                "notes": strategy.notes, "forced_offer_id": forced_offer_id})

        base = Draft(draft_id=draft_id, customer_id=customer_id, status=DraftStatus.BLOCKED,
                     objective=strategy.objective, tone=strategy.tone, template_id=strategy.template_id,
                     offer_id=strategy.offer.offer_id if strategy.offer else None, reminder_stage=strategy.reminder_stage,
                     facts_used=strategy.facts, strategy=strategy.model_dump(mode="json"), segment=seg.model_dump(mode="json"),
                     policy_version=strategy.policy_version)

        if strategy.blocked:  # DATA / POLICY: never call the LLM
            base.block_reasons = [b.model_dump(mode="json") for b in strategy.block_reasons]
            base.generation_mode = "not_generated"
            base.model_name = "none"
            self.drafts.insert(base)
            self.drafts.save_strategy(customer_id, draft_id, base.strategy)
            self.audit.log("DRAFT_BLOCKED", draft_id=draft_id, customer_id=customer_id, actor=actor,
                           payload={"reasons": base.block_reasons, "llm_called": False})
            return self.drafts.get(draft_id)

        guidance = []
        if self.retriever is not None:
            try:
                guidance = self.retriever.retrieve_for_strategy(strategy, top_k=int(self.settings.communication["generation"]["rag_top_k"]))
            except Exception as exc:  # retrieval is guidance only; never blocks generation
                self.audit.log("RAG_ERROR", draft_id=draft_id, customer_id=customer_id, payload={"error": str(exc)[:200]})

        def validate(content) -> ValidationReport:
            return self.validator.validate(content, strategy, profile, seg, history, draft_id=draft_id)

        outcome: GenerationOutcome = self.generation.generate(strategy, self._provider_for(fault), validate, guidance, feedback)
        report = outcome.report
        # Advisory tone judge on the final candidate (only when deterministic checks pass)
        if report and report.passed and self.settings.tone_judge_enabled and self.judge_provider.available:
            scores, judge_findings = tone_validator.judge(self.judge_provider, self.prompts, outcome.content, strategy,
                                                          int(self.settings.communication["tone_judge"]["warn_below"]))
            report = self.validator.summarise(report.findings + judge_findings, draft_id, scores)
            outcome.report = report

        status = DraftStatus.PENDING_REVIEW if outcome.passed else DraftStatus.BLOCKED
        c = outcome.content
        base.status = status
        base.subject, base.body, base.cta = (c.subject, c.body, c.cta) if c else ("", "", "")
        base.prompt_version = outcome.prompt_version
        base.model_name = outcome.model_name if outcome.mode not in ("static", "static_fallback") else \
            f"static-template (after {outcome.model_name})" if outcome.mode == "static_fallback" else "static-template"
        base.generation_mode = outcome.mode
        base.attempt_count = len(outcome.attempts)
        if not outcome.passed and report:
            base.block_reasons = [{"code": f.check, "category": f.category.value if f.category else None, "detail": f.detail}
                                  for f in report.blocking_failures]
        self.drafts.insert(base)
        self.drafts.save_strategy(customer_id, draft_id, base.strategy)
        self.drafts.add_attempts(draft_id, outcome.attempts)
        if report:
            self.drafts.add_validation(draft_id, report, "generation")
        self.audit.log("DRAFT_GENERATED", draft_id=draft_id, customer_id=customer_id, actor=actor, payload={
            "status": status.value, "mode": outcome.mode, "model": base.model_name, "prompt_version": base.prompt_version,
            "attempts": [a.model_dump(mode="json") for a in outcome.attempts], "stop_reason": outcome.stop_reason,
            "guidance": [f"{g.doc_id}:{g.section}" for g in outcome.guidance], "facts_used": strategy.facts,
            "fault_injected": fault, "feedback": feedback,
            "validation": {"passed": bool(report and report.passed), "failure_categories": report.failure_categories if report else []},
            "latency_ms": int((time.perf_counter() - started) * 1000)})
        return self.drafts.get(draft_id)

    def revalidate(self, draft: Draft, source: str, exclude_self: bool = True) -> tuple[ValidationReport, CustomerProfile]:
        """Re-run all checks with FRESH customer data and contact history."""
        profile, seg = self.classify(draft.customer_id)
        strategy = Strategy(**draft.strategy)
        history = self.history(draft.customer_id)
        content = {"subject": draft.subject, "body": draft.body, "cta": draft.cta}
        report = self.validator.validate(content, strategy, profile, seg, history, draft_id=draft.draft_id,
                                         exclude_draft_id=draft.draft_id if exclude_self else None)
        self.drafts.add_validation(draft.draft_id, report, source)
        return report, profile
