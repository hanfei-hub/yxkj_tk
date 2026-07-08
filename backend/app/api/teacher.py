import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import (
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    TeacherReviewRecord,
)
from app.services.serializers import derived_to_dict, product_to_dict, review_to_dict

router = APIRouter(prefix="/api/teacher", tags=["teacher"], dependencies=[Depends(require_role("teacher", "admin"))])


class RejectRequest(BaseModel):
    attribute_ids: list[int]
    review_comment: str = ""


@router.get("/products")
def teacher_products(db: Session = Depends(get_db)):
    products = db.scalars(
        select(FmProduct)
        .options(selectinload(FmProduct.derived_products))
        .order_by(FmProduct.rank_no)
    ).all()
    return [product_to_dict(item) for item in products]


@router.get("/products/{product_id}/derived-products")
def derived_products(product_id: int, db: Session = Depends(get_db)):
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.source_product_id == product_id)
        .order_by(DerivedProductRecommendation.weighted_score.desc())
    ).all()
    return [derived_to_dict(item) for item in items]


@router.post("/derived-products/{derived_id}/approve")
def approve(
    derived_id: int,
    user: dict = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    derived = db.get(DerivedProductRecommendation, derived_id)
    if not derived:
        raise HTTPException(status_code=404, detail="衍生品不存在")
    derived.review_status = "approved"
    derived.reviewed_by = user["id"]
    derived.reviewed_at = datetime.utcnow()
    db.flush()

    item_dict = derived_to_dict(derived)
    db.add(
        TeacherReviewRecord(
            teacher_id=user["id"],
            source_product_id=derived.source_product_id,
            recommendation_id=derived.id,
            review_result="approved",
            selected_attribute_ids="[]",
            review_comment="",
            review_snapshot=json.dumps(item_dict, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(derived)
    return {"ok": True, "item": derived_to_dict(derived)}


@router.post("/derived-products/{derived_id}/reject")
def reject(
    derived_id: int,
    payload: RejectRequest,
    user: dict = Depends(require_role("teacher", "admin")),
    db: Session = Depends(get_db),
):
    derived = db.get(DerivedProductRecommendation, derived_id)
    if not derived:
        raise HTTPException(status_code=404, detail="衍生品不存在")
    derived.review_status = "rejected"
    derived.reviewed_by = user["id"]
    derived.reviewed_at = datetime.utcnow()
    db.flush()

    item_dict = derived_to_dict(derived)
    db.add(
        TeacherReviewRecord(
            teacher_id=user["id"],
            source_product_id=derived.source_product_id,
            recommendation_id=derived.id,
            review_result="rejected",
            selected_attribute_ids=json.dumps(payload.attribute_ids, ensure_ascii=False),
            review_comment=payload.review_comment,
            review_snapshot=json.dumps(item_dict, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(derived)
    return {"ok": True, "item": derived_to_dict(derived)}


@router.get("/review-records")
def review_records(db: Session = Depends(get_db)):
    items = db.scalars(select(TeacherReviewRecord).order_by(TeacherReviewRecord.id.desc())).all()
    return [review_to_dict(item) for item in items]
