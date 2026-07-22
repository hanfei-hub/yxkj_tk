from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import (
    DerivedProductRecommendation,
    FastMossSyncLog,
    FmProduct,
    ModelCallLog,
    ProductFamily,
    TaskExecution,
    TeacherReviewRecord,
)
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.selection_derivation_service import generate_derivatives_for_product_ids
from app.services.supplier_1688_service import auto_match_pending_derived_products
from app.services.system_settings_service import get_setting_int


def count_by_status(db: Session, column: Any) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(status or ""): int(count) for status, count in rows}


def pipeline_status(db: Session) -> dict[str, Any]:
    latest_sync = db.scalar(select(FastMossSyncLog).order_by(FastMossSyncLog.id.desc()).limit(1))
    derived_count_subquery = (
        select(
            DerivedProductRecommendation.source_product_id.label("source_product_id"),
            func.count(DerivedProductRecommendation.id).label("derived_count"),
        )
        .group_by(DerivedProductRecommendation.source_product_id)
        .subquery()
    )
    products_without_enough_derivatives = db.scalar(
        select(func.count(FmProduct.id))
        .outerjoin(derived_count_subquery, FmProduct.id == derived_count_subquery.c.source_product_id)
        .where(func.coalesce(derived_count_subquery.c.derived_count, 0) < get_setting_int(db, "derivatives_per_product"))
    )
    return {
        "fastmoss": {
            "product_count": db.scalar(select(func.count(FmProduct.id))) or 0,
            "latest_sync": {
                "id": latest_sync.id,
                "status": latest_sync.status,
                "request_date": latest_sync.request_date,
                "synced_count": latest_sync.synced_count,
                "translation_success_count": latest_sync.translation_success_count,
                "translation_failed_count": latest_sync.translation_failed_count,
                "error_message": latest_sync.error_message,
                "started_at": latest_sync.started_at.isoformat() if latest_sync.started_at else None,
                "finished_at": latest_sync.finished_at.isoformat() if latest_sync.finished_at else None,
            }
            if latest_sync
            else None,
        },
        "families": {
            "family_count": db.scalar(select(func.count(ProductFamily.id))) or 0,
        },
        "derivation": {
            "derived_count": db.scalar(select(func.count(DerivedProductRecommendation.id))) or 0,
            "products_without_enough_derivatives": products_without_enough_derivatives or 0,
        },
        "supplier_1688": {
            "status_counts": count_by_status(db, DerivedProductRecommendation.supplier_search_status),
            "matched_count": db.scalar(
                select(func.count(DerivedProductRecommendation.id)).where(
                    DerivedProductRecommendation.supplier_search_status == "matched"
                )
            )
            or 0,
        },
        "review": {
            "status_counts": count_by_status(db, DerivedProductRecommendation.review_status),
            "review_record_count": db.scalar(select(func.count(TeacherReviewRecord.id))) or 0,
        },
        "tasks": {
            "status_counts": count_by_status(db, TaskExecution.status),
            "latest": [
                {
                    "id": item.id,
                    "task_type": item.task_type,
                    "status": item.status,
                    "processed_count": item.processed_count,
                    "success_count": item.success_count,
                    "failed_count": item.failed_count,
                    "elapsed_ms": item.elapsed_ms,
                    "started_at": item.started_at.isoformat() if item.started_at else None,
                    "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                    "error_message": item.error_message,
                }
                for item in db.scalars(select(TaskExecution).order_by(TaskExecution.id.desc()).limit(5)).all()
            ],
        },
        "model_calls": {
            "status_counts": count_by_status(db, ModelCallLog.status),
            "latest": [
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "model_type": item.model_type,
                    "model_name": item.model_name,
                    "status": item.status,
                    "elapsed_ms": item.elapsed_ms,
                    "prompt_chars": item.prompt_chars,
                    "response_chars": item.response_chars,
                    "image_count": item.image_count,
                    "error_message": item.error_message,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in db.scalars(select(ModelCallLog).order_by(ModelCallLog.id.desc()).limit(5)).all()
            ],
        },
    }


def pending_derivation_product_ids(
    db: Session,
    *,
    limit: int | None = None,
    min_derived_count: int | None = None,
) -> list[int]:
    limit = get_setting_int(db, "1688_batch_limit") if limit is None else int(limit)
    min_derived_count = get_setting_int(db, "derivatives_per_product") if min_derived_count is None else int(min_derived_count)
    derived_count_subquery = (
        select(
            DerivedProductRecommendation.source_product_id.label("source_product_id"),
            func.count(DerivedProductRecommendation.id).label("derived_count"),
        )
        .group_by(DerivedProductRecommendation.source_product_id)
        .subquery()
    )
    rows = db.scalars(
        select(FmProduct.id)
        .outerjoin(derived_count_subquery, FmProduct.id == derived_count_subquery.c.source_product_id)
        .where(func.coalesce(derived_count_subquery.c.derived_count, 0) < min_derived_count)
        .order_by(FmProduct.rank_no, FmProduct.id)
        .limit(max(1, int(limit)))
    ).all()
    return [int(item) for item in rows]


def run_supplier_match_batch(
    *,
    limit: int | None = None,
    threshold: float | None = None,
    max_candidates: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    limit = get_setting_int(db, "1688_batch_limit") if limit is None else int(limit)
    with SessionLocal() as db:
        task = create_task(
            db,
            task_type="supplier_1688_match",
            task_name="1688货源匹配",
            trigger_source="background",
            total_count=limit,
            input_snapshot={
                "limit": limit,
                "threshold": threshold,
                "max_candidates": max_candidates,
                "page_size": page_size,
            },
        )
        started = start_timer()
        try:
            result = auto_match_pending_derived_products(
                db,
                limit=limit,
                threshold=threshold,
                max_candidates=max_candidates,
                page_size=page_size,
                task_id=task.id,
            )
            failed_count = int(result.get("failed_count") or 0)
            finish_task(
                db,
                task,
                status="failed" if failed_count else "success",
                processed_count=int(result.get("count") or 0),
                success_count=max(0, int(result.get("count") or 0) - failed_count),
                failed_count=failed_count,
                elapsed_ms_value=elapsed_ms(started),
                result_snapshot=result,
                error_message="" if not failed_count else "部分1688匹配失败",
            )
            result["task_id"] = task.id
            return result
        except Exception as exc:
            finish_task(
                db,
                task,
                status="failed",
                elapsed_ms_value=elapsed_ms(started),
                result_snapshot={},
                error_message=str(exc),
            )
            raise
