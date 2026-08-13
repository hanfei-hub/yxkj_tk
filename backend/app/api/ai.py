from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import SessionLocal
from app.core.database import get_db
from app.models.entities import CreditTransaction, DerivedProductAttributeScore, DerivedProductRecommendation, FmProduct, TaskExecution, User, UserSearchRecommendation
from app.services.ai_selection_task_service import run_ai_selection_task, start_ai_selection_task, user_search_result_to_dict
from app.services.selection_derivation_service import generate_derivatives_for_products
from app.services.fastmoss_service import prepare_product_for_derivation
from app.services.supplier_1688_service import auto_match_1688_for_derived
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.serializers import derived_to_dict

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_role("admin", "teacher", "student"))])
ALLOWED_SELECTION_COUNTS = {10, 15, 20}


def selection_credit_cost(count: int) -> int:
    return count


class ChatSelectionRequest(BaseModel):
    message: str
    count: int = 10


class LibraryProductRequest(BaseModel):
    product: dict[str, Any]


@router.post("/chat-selection")
def chat_selection(
    payload: ChatSelectionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if payload.count not in ALLOWED_SELECTION_COUNTS:
        raise HTTPException(status_code=400, detail="推荐条数只能选择 10、15 或 20 条")
    requested_count = int(payload.count)
    credit_cost = selection_credit_cost(requested_count)
    user_id = int(user.get("id") or 0)
    db_user = db.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if int(db_user.credit_balance or 0) < credit_cost:
        raise HTTPException(status_code=400, detail="积分不足，请先充值")
    db_user.credit_balance = int(db_user.credit_balance or 0) - credit_cost
    db.add(CreditTransaction(
        user_id=db_user.id,
        transaction_type="consume",
        credits=-credit_cost,
        balance_after=int(db_user.credit_balance),
        source="ai_selection",
        remark=f"智能选品 {requested_count} 条",
    ))
    db.commit()
    task = start_ai_selection_task(db, message, user_id=user_id, requested_count=requested_count)
    background_tasks.add_task(run_ai_selection_task, task.id, message, user_id, credit_cost, requested_count)
    return {
        "ok": True,
        "mode": "background_task",
        "task_id": task.id,
        "status": task.status,
        "progress": 0,
        "credit_balance": db_user.credit_balance,
        "credit_cost": credit_cost,
        "requested_count": requested_count,
        "message": f"已开始 AI 智能选品，将生成 {requested_count} 个商品",
    }


@router.get("/selection-tasks/{task_id}")
def selection_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    task = db.get(TaskExecution, task_id)
    if not task or task.task_type != "ai_selection":
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        result = json.loads(task.result_snapshot or "{}")
        input_snapshot = json.loads(task.input_snapshot or "{}")
    except ValueError:
        result = {}
        input_snapshot = {}
    owner_id = int(input_snapshot.get("user_id") or 0)
    if user.get("role") != "admin" and owner_id and owner_id != int(user.get("id") or 0):
        raise HTTPException(status_code=403, detail="无权查看该任务")
    total = max(int(task.total_count or 1), 1)
    progress = int(result.get("progress") or min(99, int((task.processed_count or 0) * 100 / total)))
    if task.status == "success":
        progress = 100
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "progress": progress,
        "stage": result.get("stage") or "",
        "message": result.get("message") or "",
        "processed_count": task.processed_count,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "elapsed_ms": task.elapsed_ms,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


@router.get("/search-results")
def my_search_results(
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    user_id = int(user.get("id") or 0)
    db.execute(delete(UserSearchRecommendation).where(UserSearchRecommendation.created_at < datetime.utcnow() - timedelta(days=7)))
    db.commit()
    items = db.scalars(
        select(UserSearchRecommendation)
        .where(UserSearchRecommendation.user_id == user_id)
        .order_by(UserSearchRecommendation.created_at.desc(), UserSearchRecommendation.sort_order, UserSearchRecommendation.id)
    ).all()
    return [user_search_result_to_dict(item) for item in items]


@router.post("/library-products")
def add_library_product(
    payload: LibraryProductRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    product = payload.product or {}
    title = str(product.get("title") or product.get("derived_title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="商品名称不能为空")
    report = product.get("analysis_report") or {}
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except ValueError:
            report = {}
    if not isinstance(report, dict):
        report = {}
    report = dict(report)
    source_type = str(product.get("source_type") or ("new_product" if product.get("list_type") else "ai_search")).lower()
    is_rank_product = source_type == "new_product" or bool(product.get("list_type"))
    if is_rank_product:
        source_type = "new_product"
        region = str(product.get("region") or report.get("_library_region") or report.get("region") or "JP").upper()
        currency = str(product.get("currency") or report.get("_library_currency") or report.get("currency") or ("JPY" if region == "JP" else "")).upper()
        search_query = "榜单加入选品库"
    else:
        source_type = "ai_search"
        region = "CN"
        currency = "CNY"
        search_query = "AI搜索加入选品库"
    report["_library_region"] = region
    report["_library_currency"] = currency
    report["_library_category"] = str(product.get("category") or "")
    item = UserSearchRecommendation(
        user_id=int(user.get("id") or 0),
        task_id=None,
        search_query=search_query,
        source_type=source_type,
        title=title,
        image_url=str(product.get("image_url") or product.get("supplier_image_url") or product.get("product_image") or ""),
        price=float(product.get("price") or product.get("supplier_price") or product.get("sale_price") or 0),
        sales_count=int(float(product.get("sales_count") or product.get("supplier_sales_count") or 0)),
        reason_summary="来自 FastMoss 榜单，已加入当前账号选品库。",
        region=region,
        currency=currency,
        analysis_report=json.dumps(report, ensure_ascii=False),
        sort_order=0,
        created_at=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user_search_result_to_dict(item)


@router.get("/products/{product_id}/derived-products")
def user_visible_derived_products(
    product_id: int,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    """Return public derivations plus the current user's private derivations."""
    user_id = int(user.get("id") or 0)
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(
            DerivedProductRecommendation.source_product_id == product_id,
            DerivedProductRecommendation.review_status != "rejected",
            (DerivedProductRecommendation.owner_user_id.is_(None) | (DerivedProductRecommendation.owner_user_id == user_id)),
        )
        .order_by(DerivedProductRecommendation.weighted_score.desc(), DerivedProductRecommendation.id.desc())
    ).all()
    return [derived_to_dict(item) for item in items]


@router.post("/products/{product_id}/generate-derived")
def generate_derived(
    product_id: int,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在")
    try:
        prepare_product_for_derivation(db, product)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"商品翻译/分族失败：{exc}") from exc
    owner_user_id = int(user.get("id") or 0) or None
    result = generate_derivatives_for_products(db, [product], owner_user_id=owner_user_id)
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(
            DerivedProductRecommendation.source_product_id == product_id,
            DerivedProductRecommendation.owner_user_id == owner_user_id,
        )
        .order_by(DerivedProductRecommendation.weighted_score.desc(), DerivedProductRecommendation.id.desc())
    ).all()
    return {
        "ok": True,
        "model_used": bool(result.get("model_used")),
        "count": len(items),
        "items": [derived_to_dict(item) for item in items],
        "generation_result": result,
    }


def run_product_full_pipeline(product_id: int, task_id: int, owner_user_id: int | None = None) -> None:
    """Run lazy translation/family assignment, derivation, and 1688 matching."""
    with SessionLocal() as db:
        task = db.get(TaskExecution, task_id)
        started = start_timer()
        try:
            product = db.get(FmProduct, product_id)
            if not product:
                raise RuntimeError("原商品不存在")
            task.result_snapshot = json.dumps({"progress": 8, "stage": "translation", "message": "正在翻译标题并识别商品族"}, ensure_ascii=False)
            db.commit()
            prepare_product_for_derivation(db, product, task_id=task_id)
            task.result_snapshot = json.dumps({"progress": 28, "stage": "derivation", "message": "正在生成 10 个衍生品方向"}, ensure_ascii=False)
            db.commit()
            generation = generate_derivatives_for_products(
                db,
                [product],
                task_id=task_id,
                owner_user_id=owner_user_id,
            )
            if not int(generation.get("generated_count") or 0):
                raise RuntimeError(str(generation.get("error") or "衍生品生成失败"))
            derived_ids = list(
                db.scalars(
                    select(DerivedProductRecommendation.id)
                    .where(DerivedProductRecommendation.source_product_id == product_id)
                    .where(DerivedProductRecommendation.owner_user_id == owner_user_id)
                    .order_by(DerivedProductRecommendation.id.desc())
                ).all()
            )
            task.total_count = max(2, len(derived_ids) + 1)
            task.processed_count = 1
            task.success_count = 1
            task.result_snapshot = json.dumps({"progress": 35, "stage": "supplier_match", "message": "正在进行 1688 图片匹配", "derived_count": len(derived_ids)}, ensure_ascii=False)
            db.commit()
            failed = 0
            for index, derived_id in enumerate(derived_ids, start=1):
                try:
                    auto_match_1688_for_derived(db, derived_id, task_id=task_id)
                except Exception:
                    failed += 1
                task.processed_count = index + 1
                task.success_count = max(1, task.processed_count - failed)
                task.failed_count = failed
                progress = min(99, 35 + int(index * 64 / max(1, len(derived_ids))))
                task.result_snapshot = json.dumps({"progress": progress, "stage": "supplier_match", "message": f"1688 匹配进度 {index}/{len(derived_ids)}", "derived_count": len(derived_ids)}, ensure_ascii=False)
                db.commit()
            finish_task(
                db,
                task,
                status="failed" if failed == len(derived_ids) else "success",
                processed_count=task.total_count,
                success_count=max(1, task.total_count - failed),
                failed_count=failed,
                elapsed_ms_value=elapsed_ms(started),
                result_snapshot={"progress": 100, "stage": "completed", "message": "翻译、分族、衍生和 1688 匹配完成", "derived_count": len(derived_ids)},
                error_message="部分 1688 商品匹配失败" if failed else "",
            )
        except Exception as exc:
            finish_task(db, task, status="failed", processed_count=task.processed_count if task else 0, failed_count=1, elapsed_ms_value=elapsed_ms(started), result_snapshot={"progress": 100, "stage": "failed", "message": str(exc)}, error_message=str(exc))


@router.post("/products/{product_id}/generate-full-task")
def generate_full_task(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在")
    db_user = db.get(User, int(user.get("id") or 0))
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if int(db_user.credit_balance or 0) < 10:
        raise HTTPException(status_code=400, detail="积分不足，请先到个人中心充值积分")
    db_user.credit_balance = int(db_user.credit_balance or 0) - 10
    db.add(CreditTransaction(
        user_id=db_user.id,
        transaction_type="consume",
        credits=-10,
        balance_after=int(db_user.credit_balance),
        source="derived_pipeline",
        reference_id=product_id,
        remark="开始商品衍生",
    ))
    owner_user_id = int(user.get("id") or 0) or None
    task = create_task(
        db,
        task_type="product_full_pipeline",
        task_name="单品完整衍生",
        trigger_source="product_click",
        total_count=2,
        input_snapshot={"product_id": product_id, "user_id": owner_user_id},
    )
    db.commit()
    background_tasks.add_task(run_product_full_pipeline, product_id, task.id, owner_user_id)
    return {"ok": True, "task_id": task.id, "status": task.status, "progress": 0, "credit_cost": 10, "credit_balance": db_user.credit_balance}


@router.get("/product-full-tasks/{task_id}")
def product_full_task_status(
    task_id: int,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    task = db.get(TaskExecution, task_id)
    if not task or task.task_type != "product_full_pipeline":
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        snapshot = json.loads(task.input_snapshot or "{}")
    except ValueError:
        snapshot = {}
    owner_user_id = int(snapshot.get("user_id") or 0)
    if owner_user_id and owner_user_id != int(user.get("id") or 0) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权查看该衍生任务")
    try:
        result = json.loads(task.result_snapshot or "{}")
    except ValueError:
        result = {}
    progress = 100 if task.status == "success" else int(result.get("progress") or 0)
    return {"id": task.id, "status": task.status, "progress": progress, "stage": result.get("stage", ""), "message": result.get("message", ""), "error_message": task.error_message, "processed_count": task.processed_count, "success_count": task.success_count, "failed_count": task.failed_count}
