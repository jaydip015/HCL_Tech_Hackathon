"""Offers, strategy and draft generation API (Person 3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import container, http_error, require_customer
from backend.services.container import Container
from modules.generation.simulators import FAULTS

router = APIRouter(tags=["offers, strategy, generation (Person 3)"])


class StrategyRequest(BaseModel):
    forced_offer_id: str | None = Field(None, max_length=40)


class DraftRequest(BaseModel):
    forced_offer_id: str | None = Field(None, max_length=40)
    inject_fault: str | None = Field(None, description=f"Demo only: one of {list(FAULTS)}")
    supersede: bool = False
    requested_by: str = Field("api", max_length=64)


@router.get("/offers")
def offers(c: Container = Depends(container)):
    return {"catalog_version": c.offers.version, "global_rules": c.offers.rules,
            "offers": [o.model_dump(mode="json") for o in c.offers.all()]}


@router.post("/customers/{customer_id}/strategy")
def strategy(customer_id: str, body: StrategyRequest | None = None, c: Container = Depends(container)):
    require_customer(c, customer_id)
    _, seg, st, _ = c.engagement.decide(customer_id, (body or StrategyRequest()).forced_offer_id)
    return {"segment": seg.model_dump(mode="json"), "strategy": st.model_dump(mode="json")}


@router.post("/customers/{customer_id}/draft", status_code=201)
def create_draft(customer_id: str, body: DraftRequest | None = None, c: Container = Depends(container)):
    require_customer(c, customer_id)
    body = body or DraftRequest()
    if body.inject_fault and body.inject_fault not in FAULTS:
        raise HTTPException(status_code=422, detail=f"inject_fault must be one of {list(FAULTS)}")
    try:
        d = c.engagement.create_draft(customer_id, forced_offer_id=body.forced_offer_id, fault=body.inject_fault,
                                      actor=body.requested_by, supersede=body.supersede)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)
    return {"draft": d.model_dump(mode="json"), "validation": (r.model_dump(mode="json") if (r := c.drafts.latest_validation(d.draft_id)) else None),
            "attempts": c.drafts.attempts(d.draft_id)}
