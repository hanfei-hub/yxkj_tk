import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DailyRecommendation, FastMossSyncLog, FmProduct
from app.services.fastmoss_service import (
    FastMossError,
    get_fastmoss_config,
    request_new_listed,
    upsert_new_listed_products,
)
from app.services.serializers import daily_to_dict, fastmoss_sync_log_to_dict, product_to_dict

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


def create_sync_log(
    db: Session,
    *,
    status: str,
    page: int,
    pagesize: int,
    started_at: datetime,
    raw: dict,
    stats: dict[str, int] | None = None,
    error_message: str = "",
) -> FastMossSyncLog:
    request_payload = raw.get("request", {}) if isinstance(raw, dict) else {}
    request_date = str(request_payload.get("filter", {}).get("date_info", {}).get("value", ""))
    stats = stats or {}
    log = FastMossSyncLog(
        status=status,
        request_date=request_date,
        page=page,
        pagesize=pagesize,
        requested_count=int(stats.get("requested_count", 0)),
        synced_count=int(stats.get("synced_count", 0)),
        translation_success_count=int(stats.get("translation_success_count", 0)),
        translation_failed_count=int(stats.get("translation_failed_count", 0)),
        error_message=error_message,
        request_snapshot=json.dumps(request_payload, ensure_ascii=False),
        response_snapshot=json.dumps(raw.get("response", {}) if isinstance(raw, dict) else {}, ensure_ascii=False)[:8000],
        started_at=started_at,
        finished_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.post("/fastmoss/sync-products", dependencies=[Depends(require_role("admin"))])
def sync_fastmoss_products(
    page: int = Query(1, ge=1),
    pagesize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    started_at = datetime.utcnow()
    raw: dict = {}
    stats = {
        "requested_count": 0,
        "synced_count": 0,
        "translation_success_count": 0,
        "translation_failed_count": 0,
    }
    try:
        config = get_fastmoss_config(db)
        raw = request_new_listed(config, page=page, page_size=pagesize)
        stats = upsert_new_listed_products(db, raw)
    except FastMossError as exc:
        db.rollback()
        log = create_sync_log(
            db,
            status="failed",
            page=page,
            pagesize=pagesize,
            started_at=started_at,
            raw=raw,
            stats=stats,
            error_message=str(exc),
        )
        raise HTTPException(status_code=400, detail={"message": str(exc), "sync_log_id": log.id}) from exc

    total = db.scalar(select(func.count(FmProduct.id)))
    log = create_sync_log(
        db,
        status="success",
        page=page,
        pagesize=pagesize,
        started_at=started_at,
        raw=raw,
        stats=stats,
    )
    return {
        "ok": True,
        "message": "已同步 FastMoss 日本区新品榜：跨境商品=是，全托管商品=否。",
        "sync_log_id": log.id,
        "synced_count": stats["synced_count"],
        "requested_count": stats["requested_count"],
        "translation_success_count": stats["translation_success_count"],
        "translation_failed_count": stats["translation_failed_count"],
        "total_count": total,
        "request": raw.get("request", {}),
    }


@router.get("/fastmoss/sync-logs", dependencies=[Depends(require_role("admin"))])
def fastmoss_sync_logs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items = db.scalars(select(FastMossSyncLog).order_by(FastMossSyncLog.id.desc()).limit(limit)).all()
    return [fastmoss_sync_log_to_dict(item) for item in items]
