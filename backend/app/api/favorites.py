from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import FavoriteProduct
from app.services.serializers import favorite_to_dict


router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavoriteCreate(BaseModel):
    source_type: str = "derived"
    title: str = ""
    image_url: str = ""
    price: float = 0
    currency: str = "JPY"
    sales_count: int = 0
    category: str = ""
    recommendation_reason: str = ""
    analysis_report: Any = Field(default_factory=dict)
    product_snapshot: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def list_favorites(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(
        select(FavoriteProduct)
        .where(FavoriteProduct.user_id == user["id"])
        .order_by(FavoriteProduct.created_at.desc(), FavoriteProduct.id.desc())
    ).all()
    return [favorite_to_dict(item) for item in items]


@router.post("")
def create_favorite(
    payload: FavoriteCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blocked_keys = {"id", "source_product_id", "derived_id", "recommendation_id", "product_id"}
    snapshot = {key: value for key, value in payload.product_snapshot.items() if key not in blocked_keys}
    item = FavoriteProduct(
        user_id=user["id"],
        source_type=payload.source_type,
        title=payload.title,
        image_url=payload.image_url,
        price=payload.price,
        currency=payload.currency,
        sales_count=payload.sales_count,
        category=payload.category,
        recommendation_reason=payload.recommendation_reason,
        analysis_report=json.dumps(payload.analysis_report, ensure_ascii=False),
        product_snapshot=json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return favorite_to_dict(item)


@router.delete("/{favorite_id}")
def delete_favorite(
    favorite_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(FavoriteProduct).where(
            FavoriteProduct.id == favorite_id,
            FavoriteProduct.user_id == user["id"],
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="收藏不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": favorite_id}
