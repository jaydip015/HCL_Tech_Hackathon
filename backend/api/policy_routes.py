"""Customer-specific policy Q&A API (Person 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import container, http_error, require_customer
from backend.services.container import Container

router = APIRouter(tags=["policy RAG (Person 2)"])


class PolicyQuery(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(4, ge=1, le=8)


@router.post("/customers/{customer_id}/policy-query")
def policy_query(customer_id: str, body: PolicyQuery, c: Container = Depends(container)):
    require_customer(c, customer_id)
    try:
        ans = c.policy_qa.answer(customer_id, body.question, body.top_k)
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)
    return ans.model_dump(mode="json", exclude={"decision_evidence"})


@router.get("/customers/{customer_id}/overview")
def customer_overview(customer_id: str, c: Container = Depends(container)):
    """Category decision for one customer with each rule check and the quoted policy section behind it."""
    require_customer(c, customer_id)
    try:
        return c.overview.overview(customer_id).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.get("/policies")
def policies(c: Container = Depends(container)):
    return {"documents": c.policy_manager.list_documents(), "rule_files": c.policy_manager.rule_files(),
            "index": c.retriever.stats()}
