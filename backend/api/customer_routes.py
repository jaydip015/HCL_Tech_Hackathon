"""Customer data and profile API (Person 1)."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.api.deps import container, http_error, require_customer
from backend.services.bootstrap import load_csv
from backend.services.container import Container
from modules.data_engineering.data_loader import MappingError
from modules.profile_builder.profile_builder import profile_to_public_dict

router = APIRouter(tags=["customers (Person 1)"])


@router.get("/customers")
def list_customers(q: str | None = Query(None, max_length=64), segment: str | None = Query(None, max_length=32),
                   source: str | None = Query(None, pattern="^(kaggle|sample|demo)$"),
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), c: Container = Depends(container)):
    return {"total": c.customers.count(segment, source, q), "limit": limit, "offset": offset,
            "items": c.customers.search(q, segment, source, limit, offset)}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, c: Container = Depends(container)):
    require_customer(c, customer_id)
    return profile_to_public_dict(c.engagement.profile(customer_id))


@router.post("/customers/upload")
def upload_customers(file: UploadFile = File(...), limit: int | None = Query(None, ge=1),
                     c: Container = Depends(container)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Please upload a .csv file")
    dest_dir = c.settings.data_dir / "raw" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(file.filename).name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        return load_csv(c, dest, limit=limit, source="kaggle")
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise http_error(exc)


@router.post("/customers/{customer_id}/classify")
def classify(customer_id: str, c: Container = Depends(container)):
    require_customer(c, customer_id)
    _, seg = c.engagement.classify(customer_id)
    return seg.model_dump(mode="json")
