from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.services.pipeline_service import (
    pending_derivation_product_ids,
    pipeline_status,
    run_supplier_match_batch,
)
from app.services.selection_derivation_service import generate_derivatives_for_product_ids


router = APIRouter(
    prefix="/api/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_role("admin"))],
)


class DerivationQueueRequest(BaseModel):
    limit: int | None = None
    min_derived_count: int | None = None


class SupplierMatchQueueRequest(BaseModel):
    limit: int | None = None
    threshold: float | None = None
    max_candidates: int | None = None
    page_size: int | None = None


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return pipeline_status(db)


@router.post("/derivations/queue")
def queue_pending_derivations(
    payload: DerivationQueueRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    product_ids = pending_derivation_product_ids(
        db,
        limit=payload.limit,
        min_derived_count=payload.min_derived_count,
    )
    if product_ids:
        background_tasks.add_task(generate_derivatives_for_product_ids, product_ids)
    return {
        "ok": True,
        "queued_count": len(product_ids),
        "product_ids": product_ids,
        "mode": "background_one_by_one",
    }


@router.post("/suppliers/1688/queue")
def queue_pending_supplier_matches(
    payload: SupplierMatchQueueRequest,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        run_supplier_match_batch,
        limit=payload.limit,
        threshold=payload.threshold,
        max_candidates=payload.max_candidates,
        page_size=payload.page_size,
    )
    return {
        "ok": True,
        "queued": True,
        "limit": payload.limit,
        "threshold": payload.threshold,
        "max_candidates": payload.max_candidates,
        "page_size": payload.page_size,
        "mode": "background_batch",
    }


@router.post("/suppliers/1688/run-now")
def run_supplier_matches_now(
    limit: int | None = Query(None, ge=1, le=100),
    threshold: float | None = Query(None, ge=0, le=100),
    max_candidates: int | None = Query(None, ge=1, le=500),
    page_size: int | None = Query(None, ge=1, le=100),
):
    return run_supplier_match_batch(
        limit=limit,
        threshold=threshold,
        max_candidates=max_candidates,
        page_size=page_size,
    )
