from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DailyRecommendation, FmProduct
from app.services.fastmoss_service import (
    FastMossError,
    get_fastmoss_config,
    request_new_listed,
    upsert_new_listed_products,
)
from app.services.serializers import daily_to_dict, product_to_dict

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products/hot", dependencies=[Depends(require_role("admin", "teacher", "student"))])
def hot_products(db: Session = Depends(get_db)):
    products = db.scalars(
        select(FmProduct)
        .options(selectinload(FmProduct.derived_products))
        .where(FmProduct.platform == "TikTok", FmProduct.list_type == "new")
        .order_by(FmProduct.rank_no, FmProduct.id)
    ).all()
    return [product_to_dict(item) for item in products]


@router.get("/daily-recommendations", dependencies=[Depends(require_role("student", "admin"))])
def daily_recommendations(db: Session = Depends(get_db)):
    products = db.scalars(
        select(FmProduct)
        .where(FmProduct.platform == "TikTok", FmProduct.list_type == "new")
        .order_by(FmProduct.rank_no, FmProduct.id)
        .limit(10)
    ).all()
    if products:
        return [
            {
                "id": item.id,
                "recommendation_date": item.data_date,
                "source_product_id": item.id,
                "recommendation_id": None,
                "title": item.title,
                "image_url": item.image_url,
                "price": item.price,
                "sales_count": item.sales_count,
                "reason_summary": "FastMoss 日本新品榜：跨境商品=是，全托管商品=否。",
                "sort_order": index,
            }
            for index, item in enumerate(products, start=1)
        ]
    items = db.scalars(select(DailyRecommendation).order_by(DailyRecommendation.sort_order).limit(10)).all()
    return [daily_to_dict(item) for item in items]


@router.post("/fastmoss/sync-products", dependencies=[Depends(require_role("admin"))])
def sync_fastmoss_products(
    page: int = Query(1, ge=1),
    pagesize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        config = get_fastmoss_config(db)
        raw = request_new_listed(config, page=page, page_size=pagesize)
        count = upsert_new_listed_products(db, raw)
    except FastMossError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    total = db.scalar(select(func.count(FmProduct.id)))
    return {
        "ok": True,
        "message": "已同步 FastMoss 日本区新品榜：跨境商品=是，全托管商品=否。",
        "synced_count": count,
        "total_count": total,
        "request": raw.get("request", {}),
    }
