import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DailyRecommendation, DerivedProductRecommendation, FastMossSyncLog, FmProduct, RegionConfig, SelectionDidadogProduct, SelectionPipelineTask
from app.services.fastmoss_service import (
    FastMossError,
    REGION_CODES,
    get_fastmoss_config,
    request_rank,
    upsert_rank_products,
)
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.serializers import daily_to_dict, derived_to_dict, fastmoss_sync_log_to_dict, product_to_dict
from app.services.system_settings_service import get_setting_int

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/derived-recommendations")
def derived_recommendations(
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("student", "admin", "teacher")),
):
    # Keep the recommendation set stable for the day while sharing the same
    # pool across users and rotating the set automatically at Beijing midnight.
    day_key = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    seed_bytes = hashlib.sha256(day_key.encode("utf-8")).digest()[:4]
    daily_seed = int.from_bytes(seed_bytes, "big") or 1
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(selectinload(DerivedProductRecommendation.source_product))
        .where(DerivedProductRecommendation.review_status != "rejected")
        .order_by(func.rand(daily_seed))
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
                "currency": item.supplier_currency or "CNY",
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


@router.get("/daily-recommendations")
def daily_recommendations(
    region: str = Query("JP"),
    list_type: str = Query("new"),
    category: str = Query("全部"),
    start_date: str = Query(""),
    end_date: str = Query(""),
    page: int = Query(1, ge=1),
    pagesize: int = Query(50, ge=1, le=100),
    paged: bool = Query(False),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("student", "admin", "teacher")),
):
    current_user_id = int(user.get("id") or 0)
    conditions = product_filters(region, list_type, category, start_date, end_date)
    total = db.scalar(select(func.count(FmProduct.id)).where(*conditions)) or 0
    products = db.scalars(
        select(FmProduct)
        .options(selectinload(FmProduct.derived_products))
        .where(*conditions)
        .order_by(FmProduct.rank_no, FmProduct.id)
        .offset((page - 1) * pagesize if paged else 0)
        .limit(pagesize if paged else None)
    ).all()
    if products:
        pipeline_derived_counts = dict(
            db.execute(
                select(
                    SelectionPipelineTask.source_product_id,
                    func.count(SelectionDidadogProduct.id),
                )
                .join(SelectionDidadogProduct, SelectionDidadogProduct.pipeline_task_id == SelectionPipelineTask.id)
                .where(
                    SelectionPipelineTask.pipeline_mode == "derivation",
                    SelectionPipelineTask.status == "success",
                    SelectionPipelineTask.user_id == current_user_id,
                    SelectionPipelineTask.source_product_id.is_not(None),
                    SelectionDidadogProduct.selection_status.in_(["candidate", "final", "restricted"]),
                )
                .group_by(SelectionPipelineTask.source_product_id)
            ).all()
        )
        result = [
            {
                "id": item.id,
                "recommendation_date": item.data_date,
                "source_product_id": item.id,
                "recommendation_id": None,
                "source_type": "new_product",
                "title": item.title,
                "image_url": item.image_url,
                "price": item.price,
                "currency": item.currency,
                "sales_count": item.sales_count,
                "category": item.category,
                "region": item.region,
                "list_type": item.list_type,
                "derived_count": sum(
                    1 for derived in item.derived_products
                    if derived.owner_user_id is None
                    or derived.owner_user_id == current_user_id
                ) + int(pipeline_derived_counts.get(item.id, 0)),
                "reason_summary": "FastMoss 日本新品榜：跨境商品=是，全托管商品=否。",
                "sort_order": (page - 1) * pagesize + index,
            }
            for index, item in enumerate(products, start=1)
        ]
        return {"items": result, "page": page, "pagesize": pagesize, "total": int(total), "has_more": page * pagesize < int(total)} if paged else result
    if region.upper() != "JP" or list_type.lower() != "new" or category != "全部" or start_date or end_date:
        return {"items": [], "page": page, "pagesize": pagesize, "total": 0, "has_more": False} if paged else []
    fallback_query = select(DailyRecommendation).order_by(DailyRecommendation.sort_order)
    fallback_total = db.scalar(select(func.count(DailyRecommendation.id))) or 0
    items = db.scalars(fallback_query.offset((page - 1) * pagesize if paged else 0).limit(pagesize if paged else None)).all()
    result = [daily_to_dict(item) for item in items]
    return {"items": result, "page": page, "pagesize": pagesize, "total": int(fallback_total), "has_more": page * pagesize < int(fallback_total)} if paged else result


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
    derive_limit: int | None = Query(None, ge=0, le=100),
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
                .limit(derive_limit if derive_limit is not None else pagesize)
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


@router.post("/fastmoss/sync-configured", dependencies=[Depends(require_role("admin"))])
def sync_configured_fastmoss_products(db: Session = Depends(get_db)):
    """Sync the configured regions' new-product rankings into the existing FM table."""
    pagesize = get_setting_int(db, "fastmoss_page_size")
    configured = db.scalars(
        select(RegionConfig)
        .where(RegionConfig.status == 1)
        .order_by(RegionConfig.sort_order, RegionConfig.id)
    ).all()
    if not configured:
        raise HTTPException(status_code=400, detail="没有启用的国家/地区配置。")

    config = get_fastmoss_config(db)
    results: list[dict[str, object]] = []
    total_synced = 0
    total_requested = 0
    for item in configured:
        region = str(item.region_code or "").upper()
        # FastMoss does not provide a CN ranking endpoint; keep it configurable
        # in the product filters but do not send an invalid request upstream.
        if region not in REGION_CODES:
            results.append({
                "region": region,
                "region_name": item.region_name,
                "status": "skipped",
                "message": "FastMoss 当前不支持该地区。",
                "requested_count": 0,
                "synced_count": 0,
            })
            continue
        started_at = datetime.utcnow()
        timer = start_timer()
        raw: dict = {}
        try:
            raw = request_rank(config, region=region, list_type="new", page=1, page_size=pagesize)
            stats = upsert_rank_products(db, raw, region=region, list_type="new")
            log = create_sync_log(
                db,
                status="success",
                page=1,
                pagesize=pagesize,
                started_at=started_at,
                raw=raw,
                stats=stats,
            )
            total_requested += int(stats.get("requested_count", 0))
            total_synced += int(stats.get("synced_count", 0))
            results.append({
                "region": region,
                "region_name": item.region_name,
                "status": "success",
                "requested_count": stats.get("requested_count", 0),
                "synced_count": stats.get("synced_count", 0),
                "sync_log_id": log.id,
                "elapsed_ms": elapsed_ms(timer),
            })
        except FastMossError as exc:
            db.rollback()
            stats = {"requested_count": 0, "synced_count": 0}
            log = create_sync_log(
                db,
                status="failed",
                page=1,
                pagesize=pagesize,
                started_at=started_at,
                raw=raw,
                stats=stats,
                error_message=str(exc),
            )
            results.append({
                "region": region,
                "region_name": item.region_name,
                "status": "failed",
                "message": str(exc),
                "sync_log_id": log.id,
                "elapsed_ms": elapsed_ms(timer),
            })

    failed = [item for item in results if item.get("status") == "failed"]
    successful = [item for item in results if item.get("status") == "success"]
    skipped = [item for item in results if item.get("status") == "skipped"]
    if not successful and failed:
        raise HTTPException(status_code=400, detail={
            "message": "所有可请求地区同步失败。",
            "results": results,
        })
    return {
        "ok": True,
        "message": "已按启用地区同步新品榜单。",
        "pagesize": pagesize,
        "regions": results,
        "requested_count": total_requested,
        "synced_count": total_synced,
        "success_region_count": len(successful),
        "failed_region_count": len(failed),
        "skipped_region_count": len(skipped),
    }


@router.get("/fastmoss/sync-logs", dependencies=[Depends(require_role("admin"))])
def fastmoss_sync_logs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items = db.scalars(select(FastMossSyncLog).order_by(FastMossSyncLog.id.desc()).limit(limit)).all()
    return [fastmoss_sync_log_to_dict(item) for item in items]
