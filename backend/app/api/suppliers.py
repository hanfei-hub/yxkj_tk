from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DerivedProductRecommendation
from app.services.supplier_1688_service import (
    Supplier1688Error,
    auto_match_1688_for_derived,
    auto_match_pending_derived_products,
    search_1688_products,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"], dependencies=[Depends(require_role("admin", "teacher"))])


class SupplierSearchRequest(BaseModel):
    keyword: str
    page: int = 1
    page_size: int | None = None


class SupplierAutoMatchRequest(BaseModel):
    threshold: float | None = None
    max_candidates: int | None = None
    page_size: int | None = None


class SupplierBatchAutoMatchRequest(SupplierAutoMatchRequest):
    limit: int | None = None


@router.post("/1688/search")
def search_1688(payload: SupplierSearchRequest, db: Session = Depends(get_db)):
    try:
        return search_1688_products(db, payload.keyword, page=payload.page, page_size=payload.page_size)
    except Supplier1688Error as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/1688/derived-products/auto-match")
def auto_match_pending_1688_products(
    payload: SupplierBatchAutoMatchRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or SupplierBatchAutoMatchRequest()
    try:
        return auto_match_pending_derived_products(
            db,
            limit=payload.limit,
            threshold=payload.threshold,
            max_candidates=payload.max_candidates,
            page_size=payload.page_size,
        )
    except Supplier1688Error as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/1688/derived-products/{derived_id}/search")
def search_1688_for_derived_product(
    derived_id: int,
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
):
    derived = db.get(DerivedProductRecommendation, derived_id)
    if not derived:
        raise HTTPException(status_code=404, detail="衍生品不存在。")
    keyword = (derived.derived_title or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="衍生品缺少搜索关键词。")
    try:
        result = search_1688_products(db, keyword, page=page, page_size=page_size)
    except Supplier1688Error as exc:
        derived.supplier_search_status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    derived.supplier_search_status = "has_result" if result["items"] else "no_result"
    db.commit()
    return result | {"derived_id": derived.id, "supplier_search_status": derived.supplier_search_status}


@router.post("/1688/derived-products/{derived_id}/auto-match")
def auto_match_1688_for_derived_product(
    derived_id: int,
    payload: SupplierAutoMatchRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or SupplierAutoMatchRequest()
    try:
        return auto_match_1688_for_derived(
            db,
            derived_id,
            threshold=payload.threshold,
            max_candidates=payload.max_candidates,
            page_size=payload.page_size,
        )
    except Supplier1688Error as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
