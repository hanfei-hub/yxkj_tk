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
from app.services.supplier_1688_service import Supplier1688Error, image_search_1688_products, int_value, number_value


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
    report = payload.analysis_report
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except (TypeError, ValueError):
            report = {"report_text": report}
    incoming_supplier_id = str(snapshot.get("supplier_product_id") or snapshot.get("product_id") or "").strip()
    incoming_image = str(payload.image_url or snapshot.get("image_url") or "").strip()
    existing_rows = db.scalars(
        select(FavoriteProduct).where(
            FavoriteProduct.user_id == user["id"],
            FavoriteProduct.source_type == payload.source_type,
        )
    ).all()
    for existing_item in existing_rows:
        try:
            existing_snapshot = json.loads(existing_item.product_snapshot or "{}")
        except (TypeError, ValueError):
            existing_snapshot = {}
        if incoming_supplier_id and str(existing_snapshot.get("supplier_product_id") or "").strip() == incoming_supplier_id:
            return favorite_to_dict(existing_item)
        if incoming_image and str(existing_item.image_url or "").strip() == incoming_image:
            return favorite_to_dict(existing_item)
        if existing_item.title.strip().casefold() == payload.title.strip().casefold():
            return favorite_to_dict(existing_item)
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
        analysis_report=json.dumps(report, ensure_ascii=False),
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


@router.post("/{favorite_id}/match-1688")
def match_favorite_1688(
    favorite_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Use the saved image to find a 1688 source and update this user's snapshot."""
    item = db.scalar(
        select(FavoriteProduct).where(
            FavoriteProduct.id == favorite_id,
            FavoriteProduct.user_id == user["id"],
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="采集箱商品不存在。")

    try:
        snapshot = json.loads(item.product_snapshot or "{}")
    except (TypeError, ValueError):
        snapshot = {}
    image_url = str(item.image_url or snapshot.get("image_url") or snapshot.get("supplier_image_url") or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="商品没有图片，无法匹配 1688。")

    try:
        result = image_search_1688_products(db, image_url)
    except Supplier1688Error as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    candidates = result.get("items") or []
    if not candidates:
        return {"ok": True, "matched": False, "message": "没有找到匹配的 1688 商品。", "item": favorite_to_dict(item)}

    candidate = candidates[0]
    title = str(candidate.get("title") or item.title or "")
    matched_image = str(candidate.get("image_url") or image_url)
    price = round(number_value(candidate.get("price")), 2)
    sales_count = int_value(candidate.get("sales_count"))
    source_url = str(candidate.get("source_url") or "")
    snapshot.update(
        {
            "title": title,
            "image_url": matched_image,
            "price": price,
            "currency": "CNY",
            "sales_count": sales_count,
            "region": "CN",
            "country": "中国",
            "supplier_product_id": candidate.get("supplier_product_id") or "",
            "supplier_title": title,
            "supplier_image_url": matched_image,
            "supplier_price": price,
            "supplier_currency": "CNY",
            "supplier_sales_count": sales_count,
            "supplier_shop_name": candidate.get("shop_name") or "",
            "supplier_source_url": source_url,
            "supplier_raw_data": candidate.get("raw_data") or candidate,
        }
    )
    item.title = title
    item.image_url = matched_image
    item.price = price
    item.currency = "CNY"
    item.sales_count = sales_count
    item.product_snapshot = json.dumps(snapshot, ensure_ascii=False)
    db.commit()
    db.refresh(item)
    return {
        "ok": True,
        "matched": True,
        "match_count": len(candidates),
        "item": favorite_to_dict(item),
    }
