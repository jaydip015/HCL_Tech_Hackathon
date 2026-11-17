"""Shared Pydantic contracts used by all four modules.

Changing a model here is a cross-team change: update API_CONTRACTS.md and tell the
other owners. Each model is annotated with the module that produces it.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- enums
class PaymentStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"


class DraftStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"          # failed validation/policy/data - cannot be approved or sent
    NEEDS_FIX = "NEEDS_FIX"      # a reviewer edit failed validation
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MOCK_SENT = "MOCK_SENT"
    CANCELLED = "CANCELLED"      # pre-send gate cancelled it (e.g. customer has since paid)


class FailureCategory(str, Enum):
    DATA = "DATA"
    POLICY = "POLICY"
    WRITING = "WRITING"
    FORMAT = "FORMAT"


Severity = Literal["BLOCK", "WARN", "INFO"]
CheckStatus = Literal["PASS", "FAIL", "WARN", "SKIP"]


# --------------------------------------------------------------------------- Person 1
class DataIssue(BaseModel):
    code: str
    field: str | None = None
    detail: str
    severity: Literal["BLOCK", "WARN"] = "BLOCK"


class CustomerProfile(BaseModel):
    """Standardised, verified customer context. Produced by modules/profile_builder (Person 1).

    Protected characteristics (gender, age, senior citizen, ...) are not part of this model.
    """

    customer_id: str
    customer_name: str | None = None
    email_address: str | None = None
    tenure_months: int | None = None
    contract_type: str | None = None
    payment_method: str | None = None
    monthly_charges: float | None = None
    total_charges: float | None = None
    usage_last_3m: float | None = None
    usage_prev_3m: float | None = None
    last_active_date: date | None = None
    bill_due_date: date | None = None
    amount_due: float | None = None
    payment_status: str | None = None
    on_time_payment_ratio: float | None = None
    marketing_consent: bool | None = None
    last_contacted_date: date | None = None
    churn_status: int | None = None
    customer_service_calls: int | None = None
    num_complaints: float | None = None
    customer_satisfaction: float | None = None
    customer_support_contact: str | None = None
    data_source: str | None = None

    # Derived at build time relative to settings.as_of_date
    as_of_date: date | None = None
    days_since_active: int | None = None
    days_overdue: int = 0
    days_since_contact: int | None = None
    data_issues: list[DataIssue] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)

    @property
    def first_name(self) -> str:
        return (self.customer_name or "Customer").split()[0]

    @property
    def has_blocking_issue(self) -> bool:
        return any(i.severity == "BLOCK" for i in self.data_issues)


# --------------------------------------------------------------------------- Person 2
class RuleEvidence(BaseModel):
    segment: str
    reason_code: str
    field: str
    operator: str
    threshold: Any
    actual: Any
    passed: bool
    near_threshold: bool = False
    policy_ref: str | None = None


class SegmentResult(BaseModel):
    customer_id: str
    status: Literal["CLASSIFIED", "MANUAL_REVIEW"]
    segments: list[str] = Field(default_factory=list)
    primary_segment: str | None = None
    secondary_segments: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[RuleEvidence] = Field(default_factory=list)
    confidence: float = 0.0
    manual_review_reasons: list[str] = Field(default_factory=list)
    churn_status_info: int | None = None  # supplementary only - never drives treatment
    policy_version: str = ""


class PolicySource(BaseModel):
    doc_id: str
    doc_name: str
    section: str
    version: str
    excerpt: str
    score: float


class PolicyAnswer(BaseModel):
    customer_id: str
    question: str
    answer: str
    insufficient_evidence: bool = False
    sources: list[PolicySource] = Field(default_factory=list)
    decision_evidence: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["llm", "deterministic"] = "deterministic"
    model_name: str | None = None


class PolicyQuote(BaseModel):
    """Exact text of one policy section, quoted from the knowledge base (not paraphrased)."""
    ref: str
    doc_id: str
    doc_name: str
    section: str
    version: str
    text: str


class ConditionCheck(BaseModel):
    reason_code: str
    field: str
    label: str
    operator: str
    threshold: str
    actual: str
    passed: bool
    near_threshold: bool = False
    explanation: str


class SegmentCheck(BaseModel):
    segment: str
    description: str = ""
    evaluated: bool = True
    matched: bool
    is_primary: bool = False
    conditions: list[ConditionCheck] = Field(default_factory=list)
    policy: PolicyQuote | None = None


class OverviewReason(BaseModel):
    reason: str
    policy: PolicyQuote | None = None


class CustomerOverview(BaseModel):
    """Deterministic category decision for one customer with the policy proof behind it."""
    customer_id: str
    status: Literal["CLASSIFIED", "MANUAL_REVIEW"]
    primary_segment: str | None = None
    secondary_segments: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    headline: str
    priority: list[str] = Field(default_factory=list)
    segment_checks: list[SegmentCheck] = Field(default_factory=list)
    manual_review_reasons: list[OverviewReason] = Field(default_factory=list)
    priority_policy: PolicyQuote | None = None
    objective: str | None = None
    tone: str | None = None
    reminder_stage: int | None = None
    offer: str | None = None
    blocked: bool = False
    block_reasons: list[OverviewReason] = Field(default_factory=list)
    strategy_policies: list[PolicyQuote] = Field(default_factory=list)
    key_facts: dict[str, str] = Field(default_factory=dict)
    data_issues: list[str] = Field(default_factory=list)
    data_source: str | None = None
    policy_version: str = ""


# --------------------------------------------------------------------------- Person 3
class Offer(BaseModel):
    offer_id: str
    name: str
    value: str
    description: str = ""
    terms: str
    eligible_segments: list[str]
    min_tenure_months: int = 0
    start_date: date
    expiry_date: date
    channels: list[str] = Field(default_factory=lambda: ["EMAIL"])
    status: str = "ACTIVE"


class OfferDecision(BaseModel):
    offer_id: str
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class BlockReason(BaseModel):
    code: str
    category: FailureCategory
    detail: str
    policy_ref: str | None = None


class Strategy(BaseModel):
    customer_id: str
    primary_segment: str | None
    objective: str | None = None
    tone: str | None = None
    template_id: str | None = None
    reminder_stage: int | None = None
    is_marketing: bool = False
    offer: Offer | None = None
    offer_decisions: list[OfferDecision] = Field(default_factory=list)
    blocked: bool = False
    block_reasons: list[BlockReason] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    policy_refs: list[str] = Field(default_factory=list)
    policy_version: str = ""


class EmailContent(BaseModel):
    """Structured LLM output contract."""

    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=4000)
    cta: str = Field(default="", max_length=200)


class GenerationAttempt(BaseModel):
    attempt_no: int
    mode: Literal["llm", "repair", "format_retry", "static_fallback", "static", "reviewer_regenerate"]
    model_name: str
    prompt_version: str
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    passed: bool = False
    failure_categories: list[str] = Field(default_factory=list)
    error: str | None = None


# --------------------------------------------------------------------------- Person 4
class ValidationFinding(BaseModel):
    check: str
    status: CheckStatus
    severity: Severity = "BLOCK"
    category: FailureCategory | None = None
    detail: str = ""


class ValidationReport(BaseModel):
    draft_id: str | None = None
    passed: bool
    findings: list[ValidationFinding] = Field(default_factory=list)
    retry_recommended: bool = False
    failure_categories: list[str] = Field(default_factory=list)
    tone_scores: dict[str, Any] | None = None
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    @property
    def blocking_failures(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.status == "FAIL" and f.severity == "BLOCK"]

    @property
    def warnings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.status == "WARN" or (f.status == "FAIL" and f.severity == "WARN")]


class ContactRecord(BaseModel):
    customer_id: str
    draft_id: str | None = None
    template_id: str | None = None
    objective: str | None = None
    is_marketing: bool = False
    content_hash: str | None = None
    sent_at: datetime


class Draft(BaseModel):
    draft_id: str
    customer_id: str
    status: DraftStatus
    subject: str = ""
    body: str = ""
    cta: str = ""
    objective: str | None = None
    tone: str | None = None
    template_id: str | None = None
    offer_id: str | None = None
    reminder_stage: int | None = None
    facts_used: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] = Field(default_factory=dict)
    segment: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str | None = None
    model_name: str | None = None
    policy_version: str | None = None
    generation_mode: str | None = None
    attempt_count: int = 0
    block_reasons: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=64)
    reason: str | None = None
    feedback: str | None = None
    subject: str | None = None
    body: str | None = None
    cta: str | None = None
