import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DailyRecommendation, DerivedProductRecommendation, FastMossSyncLog, FmProduct
from app.services.fastmoss_service import (
    FastMossError,
    get_fastmoss_config,
    request_rank,
    upsert_rank_products,
)
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.serializers import daily_to_dict, derived_to_dict, fastmoss_sync_log_to_dict, product_to_dict
from app.services.system_settings_service import get_setting_int

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/derived-recommendations", dependencies=[Depends(require_role("student", "admin", "teacher"))])
def derived_recommendations(limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(selectinload(DerivedProductRecommendation.source_product))
        .where(DerivedProductRecommendation.review_status != "rejected")
        .order_by(func.rand())
        .limit(limit)
    ).all()
    result = []
    for item in items:
        row = derived_to_dict(item)
        row.update(
            {
                "title": item.derived_title,
                # 1688 尚未匹配完成时，先用原商品图作为可视化回退，匹配成功后优先使用供应商首图。
                "image_url": item.supplier_image_url or (item.source_product.image_url if item.source_product else "") or "",
                "price": item.supplier_price or item.suggested_price_min or 0,
                "sales_count": item.supplier_sales_count or 0,
                "reference_image_url": item.source_product.image_url if item.source_product else "",
                "region": item.source_product.region if item.source_product else "JP",
                "category": item.source_product.category if item.source_product else "",
            }
        )
        result.append(row)
    return result

CATEGORY_FILTERS = {
    "美妆个护": "Beauty & Personal Care", "女装与女士内衣": "Womenswear & Underwear", "保健": "Health",
    "时尚配件": "Fashion Accessories", "运动与户外": "Sports & Outdoor", "手机与数码": "Phones & Electronics",
    "居家日用": "Home Supplies", "食品饮料": "Food & Beverage", "汽车与摩托车": "Automotive & Motorcycle",
    "男装与男士内衣": "Menswear & Underwear", "收藏品": "Collectibles", "玩具和爱好": "Toys & Hobbies",
}


def product_filters(region: str, list_type: str, category: str, start_date: str = "", end_date: str = ""):
    conditions = [FmProduct.platform == "TikTok", FmProduct.list_type == list_type.lower()]
    if region.upper() != "ALL":
        conditions.append(FmProduct.region == region.upper())
    if category and category != "全部":
        conditions.append(FmProduct.category.ilike(f"%{CATEGORY_FILTERS.get(category, category)}%"))
    if start_date:
        conditions.append(FmProduct.data_date >= start_date)
    if end_date:
        conditions.append(FmProduct.data_date <= end_date)
    return conditions


@router.get("/products/hot", dependencies=[Depends(require_role("admin", "teacher", "student"))])
def hot_products(region: str = Query("JP"), list_type: str = Query("new"), category: str = Query("全部"), start_date: str = Query(""), end_date: str = Query(""), db: Session = Depends(get_db)):
    products = db.scalars(
        select(FmProduct)
        .options(selectinload(FmProduct.derived_products))
        .where(*product_filters(region, list_type, category, start_date, end_date))
        .order_by(FmProduct.rank_no, FmProduct.id)
    ).all()
    return [product_to_dict(item) for item in products]


@router.get("/daily-recommendations", dependencies=[Depends(require_role("student", "admin", "teacher"))])
def daily_recommendations(region: str = Query("JP"), list_type: str = Query("new"), category: str = Query("全部"), start_date: str = Query(""), end_date: str = Query(""), db: Session = Depends(get_db)):
    products = db.scalars(
        select(FmProduct)
        .where(*product_filters(region, list_type, category, start_date, end_date))
        .order_by(FmProduct.rank_no, FmProduct.id)
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
                "category": item.category,
                "region": item.region,
                "list_type": item.list_type,
                "reason_summary": "FastMoss 日本新品榜：跨境商品=是，全托管商品=否。",
                "sort_order": index,
            }
            for index, item in enumerate(products, start=1)
        ]
    if region.upper() != "JP" or list_type.lower() != "new" or category != "全部" or start_date or end_date:
        return []
    items = db.scalars(select(DailyRecommendation).order_by(DailyRecommendation.sort_order)).all()
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
    background_tasks: BackgroundTasks,
    page: int = Query(1, ge=1),
    pagesize: int | None = Query(None, ge=1, le=100),
    region: str = Query("JP"),
    list_type: str = Query("new"),
    db: Session = Depends(get_db),
):
    pagesize = pagesize or get_setting_int(db, "fastmoss_page_size")
    started_at = datetime.utcnow()
    timer = start_timer()
    task = create_task(
        db,
        task_type="fastmoss_sync",
        task_name="FastMoss新品榜同步",
        trigger_source="api",
        total_count=pagesize,
        input_snapshot={"page": page, "pagesize": pagesize, "region": region.upper(), "list_type": list_type.lower()},
    )
    raw: dict = {}
    stats = {
        "requested_count": 0,
        "synced_count": 0,
        "translation_success_count": 0,
        "translation_failed_count": 0,
    }
    try:
        config = get_fastmoss_config(db)
        raw = request_rank(config, region=region, list_type=list_type, page=page, page_size=pagesize)
        stats = upsert_rank_products(db, raw, region=region, list_type=list_type)
        request_date = str(raw.get("request", {}).get("filter", {}).get("date_info", {}).get("value", ""))
        # FastMoss sync is raw ingestion only. Translation/family/derivation starts from a product click.
        if False and stats.get("synced_count", 0):
            synced_product_ids = list(
                db.scalars(
                select(FmProduct.id)
                .where(FmProduct.platform == "TikTok", FmProduct.list_type == "new", FmProduct.data_date == request_date)
                .order_by(FmProduct.rank_no, FmProduct.id)
                .limit(pagesize)
                ).all()
            )
            if synced_product_ids:
                derivation_task = create_task(
                    db,
                    task_type="derivation_generate",
                    task_name="衍生品生成",
                    trigger_source="fastmoss_sync",
                    total_count=len(synced_product_ids),
                    input_snapshot={"product_ids": synced_product_ids, "sync_task_id": task.id},
                )
                background_tasks.add_task(generate_derivatives_for_product_ids, synced_product_ids, derivation_task.id)
            stats["derivation_result"] = {
                "queued": len(synced_product_ids),
                "mode": "background_one_by_one",
                "task_id": derivation_task.id if synced_product_ids else None,
            }
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
        finish_task(
            db,
            task,
            status="failed",
            processed_count=0,
            failed_count=1,
            elapsed_ms_value=elapsed_ms(timer),
            result_snapshot={"sync_log_id": log.id},
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
    finish_task(
        db,
        task,
        status="success",
        processed_count=int(stats.get("requested_count", 0)),
        success_count=int(stats.get("synced_count", 0)),
        failed_count=max(0, int(stats.get("requested_count", 0)) - int(stats.get("synced_count", 0))),
        elapsed_ms_value=elapsed_ms(timer),
        result_snapshot={"sync_log_id": log.id, **stats},
    )
    return {
        "ok": True,
        "message": "已同步 FastMoss 日本区新品榜：跨境商品=是，全托管商品=否。",
        "sync_log_id": log.id,
        "task_id": task.id,
        "synced_count": stats["synced_count"],
        "requested_count": stats["requested_count"],
        "translation_success_count": stats["translation_success_count"],
        "translation_failed_count": stats["translation_failed_count"],
        "total_count": total,
        "derivation_result": stats.get("derivation_result", {}),
        "request": raw.get("request", {}),
    }


@router.get("/fastmoss/sync-logs", dependencies=[Depends(require_role("admin"))])
def fastmoss_sync_logs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items = db.scalars(select(FastMossSyncLog).order_by(FastMossSyncLog.id.desc()).limit(limit)).all()
    return [fastmoss_sync_log_to_dict(item) for item in items]
