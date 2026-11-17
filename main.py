"""FastAPI backend. Run: uvicorn main:app --reload --port 8000  (docs at /docs)."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from backend.api import customer_routes, generation_routes, policy_routes, review_routes
from backend.services.container import get_container

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Customer Loyalty and Engagement Assistant",
    version="1.0.0",
    description="Python decides, RAG retrieves policy, the LLM writes, validators enforce, humans approve. "
                "No real emails are ever sent.",
)
app.include_router(customer_routes.router)
app.include_router(policy_routes.router)
app.include_router(generation_routes.router)
app.include_router(review_routes.router)


@app.get("/health", tags=["system"])
def health():
    c = get_container()
    return {"status": "ok", "customers": c.customers.count(), "llm": c.llm_status, "rag": c.retriever.stats(),
            "policy_version": c.settings.policy_version, "as_of_date": c.settings.as_of_date.isoformat()}
