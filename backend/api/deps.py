"""Shared API dependencies and error mapping."""
from __future__ import annotations

from fastapi import HTTPException

from backend.services.container import Container, get_container
from backend.services.engagement_service import NotFoundError
from modules.email.mock_email_service import DeliveryError
from modules.review.review_service import ReviewError


def container() -> Container:
    return get_container()


def http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (NotFoundError, KeyError)):
        return HTTPException(status_code=404, detail=str(exc).strip("'\""))
    if isinstance(exc, (ReviewError, DeliveryError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Internal error")


def require_customer(c: Container, customer_id: str) -> None:
    if not c.customers.exists(customer_id):
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
