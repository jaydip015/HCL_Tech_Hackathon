"""Dependency container: builds every service once and shares it between Streamlit and FastAPI."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from backend.database.db import Database
from config import Settings, get_settings
from modules.audit.audit_service import AuditService
from modules.email.mock_email_service import MockEmailService
from modules.generation.email_generator import EmailGenerator, TemplateStore
from modules.generation.generation_service import GenerationService
from modules.generation.llm_client import LLMProvider, NoLLMProvider, get_provider
from modules.generation.prompt_manager import PromptManager
from modules.generation.simulators import OfflineSimulatorProvider
from modules.offers.offer_repository import OfferRepository
from modules.policy.policy_manager import PolicyManager
from modules.profile_builder.customer_repository import CustomerRepository
from modules.rag.customer_overview import CustomerOverviewService
from modules.rag.policy_qa import PolicyQAService
from modules.rag.retriever import PolicyRetriever
from modules.review.draft_repository import DraftRepository
from modules.review.review_service import ReviewService
from modules.segmentation.segmentation_engine import SegmentationEngine
from modules.strategy.strategy_selector import StrategySelector
from modules.validation.validator import EmailValidator
from backend.services.engagement_service import EngagementService

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    db: Database
    customers: CustomerRepository
    segmentation: SegmentationEngine
    offers: OfferRepository
    selector: StrategySelector
    retriever: PolicyRetriever
    policy_manager: PolicyManager
    prompts: PromptManager
    templates: TemplateStore
    provider: LLMProvider
    judge_provider: LLMProvider
    validator: EmailValidator
    drafts: DraftRepository
    audit: AuditService
    engagement: EngagementService
    review: ReviewService
    email: MockEmailService
    policy_qa: PolicyQAService
    overview: CustomerOverviewService

    @property
    def llm_status(self) -> str:
        if isinstance(self.provider, OfflineSimulatorProvider):
            return "offline simulator (testing only, not a real LLM)"
        if self.provider.available:
            return f"{self.provider.name}: {self.provider.model}"
        return "No LLM configured - approved static templates are used"


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    customers = CustomerRepository(db)
    segmentation = SegmentationEngine(settings)
    offers = OfferRepository(settings, db)
    selector = StrategySelector(settings, offers)
    retriever = PolicyRetriever(settings)
    policy_manager = PolicyManager(settings, db)
    policy_manager.register_documents()
    prompts = PromptManager(settings.prompts_dir)
    templates = TemplateStore(settings.knowledge_base_dir / "templates")
    simulator = OfflineSimulatorProvider(templates)
    if settings.llm_provider == "offline_simulator":
        provider: LLMProvider = simulator
        judge: LLMProvider = NoLLMProvider()
    else:
        provider = get_provider(settings, "generation")
        judge = get_provider(settings, "judge")
    gen_cfg = settings.communication["generation"]
    generator = EmailGenerator(prompts, templates, settings.reminders, float(gen_cfg["temperature"]), int(gen_cfg["max_tokens"]))
    generation = GenerationService(generator, templates, int(gen_cfg["max_repair_attempts"]))
    validator = EmailValidator(settings, offers)
    drafts = DraftRepository(db)
    audit = AuditService(db, settings.privacy.get("log_redact_fields"))
    engagement = EngagementService(settings, customers, segmentation, selector, retriever, generation, provider, judge,
                                   validator, drafts, audit, prompts, simulator)
    review = ReviewService(drafts, audit, engagement)
    email = MockEmailService(db, drafts, audit, engagement, customers)
    policy_qa = PolicyQAService(retriever, engagement.decision_evidence, provider if provider is not simulator else NoLLMProvider(), prompts)
    overview = CustomerOverviewService(retriever, engagement.decision_evidence, lambda: settings.segmentation)
    return Container(settings, db, customers, segmentation, offers, selector, retriever, policy_manager, prompts, templates,
                     provider, judge, validator, drafts, audit, engagement, review, email, policy_qa, overview)


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()
