"""Validation, human review, mock delivery, audit and metrics API (Person 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.deps import container, http_error
from backend.schemas.models import DraftStatus
from backend.services.container import Container
from modules.audit.metrics import compute_metrics

router = APIRouter(tags=["validation, review, delivery, audit (Person 4)"])


class Reviewer(BaseModel):
    reviewer: str = Field(min_length=1, max_length=64)


class EditBody(Reviewer):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=4000)
    cta: str | None = Field(None, max_length=200)


class RejectBody(Reviewer):
    reason: str = Field(min_length=3, max_length=500)


class RegenerateBody(Reviewer):
    feedback: str = Field(min_length=3, max_length=1000)


def _draft_or_404(c: Container, draft_id: str):
    d = c.drafts.get(draft_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    return d


@router.post("/drafts/{draft_id}/validate")
def validate(draft_id: str, c: Container = Depends(container)):
    d = _draft_or_404(c, draft_id)
    if d.generation_mode == "not_generated":
        raise HTTPException(status_code=409, detail="Draft was blocked before generation; nothing to validate.")
    report, _ = c.engagement.revalidate(d, "manual")
    return report.model_dump(mode="json")


@router.get("/review/queue")
def queue(status: list[str] | None = Query(None), limit: int = Query(100, ge=1, le=500), c: Container = Depends(container)):
    valid = {s.value for s in DraftStatus}
    if status and not set(status) <= valid:
        raise HTTPException(status_code=422, detail=f"status must be in {sorted(valid)}")
    return [d.model_dump(mode="json", include={"draft_id", "customer_id", "status", "objective", "offer_id", "subject",
                                               "generation_mode", "attempt_count", "updated_at"})
            for d in c.review.queue(status, limit)]


@router.post("/review/{draft_id}/approve")
def approve(draft_id: str, body: Reviewer, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    try:
        return c.review.approve(draft_id, body.reviewer).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.post("/review/{draft_id}/edit")
def edit(draft_id: str, body: EditBody, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    try:
        d, report = c.review.edit(draft_id, body.reviewer, body.subject, body.body, body.cta)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)
    return {"draft": d.model_dump(mode="json"), "validation": report.model_dump(mode="json")}


@router.post("/review/{draft_id}/reject")
def reject(draft_id: str, body: RejectBody, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    try:
        return c.review.reject(draft_id, body.reviewer, body.reason).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.post("/review/{draft_id}/regenerate", status_code=201)
def regenerate(draft_id: str, body: RegenerateBody, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    try:
        return c.review.regenerate(draft_id, body.reviewer, body.feedback).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.post("/send/{draft_id}")
def send(draft_id: str, body: Reviewer, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    try:
        return c.email.send(draft_id, body.reviewer)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.get("/audit/{draft_id}")
def audit(draft_id: str, c: Container = Depends(container)):
    _draft_or_404(c, draft_id)
    return c.audit.trace(draft_id)


@router.get("/metrics")
def metrics(c: Container = Depends(container)):
    return compute_metrics(c.db, c.settings.price_input_per_mtok, c.settings.price_output_per_mtok)
