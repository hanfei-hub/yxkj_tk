from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import SessionLocal
from app.core.database import get_db
from app.models.entities import DerivedProductAttributeScore, DerivedProductRecommendation, FmProduct, TaskExecution, User, UserSearchRecommendation
from app.services.ai_selection_task_service import run_ai_selection_task, start_ai_selection_task, user_search_result_to_dict
from app.services.selection_derivation_service import generate_derivatives_for_products
from app.services.fastmoss_service import prepare_product_for_derivation
from app.services.supplier_1688_service import auto_match_1688_for_derived
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.serializers import derived_to_dict

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_role("admin", "teacher", "student"))])
SEARCH_CREDIT_COST = 1


class ChatSelectionRequest(BaseModel):
    message: str


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
    user_id = int(user.get("id") or 0)
    db_user = db.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if int(db_user.credit_balance or 0) < SEARCH_CREDIT_COST:
        raise HTTPException(status_code=400, detail="积分不足，请先充值")
    db_user.credit_balance = int(db_user.credit_balance or 0) - SEARCH_CREDIT_COST
    db.commit()
    task = start_ai_selection_task(db, message, user_id=user_id)
    background_tasks.add_task(run_ai_selection_task, task.id, message, user_id, SEARCH_CREDIT_COST)
    return {
        "ok": True,
        "mode": "background_task",
        "task_id": task.id,
        "status": task.status,
        "progress": 0,
        "credit_balance": db_user.credit_balance,
        "credit_cost": SEARCH_CREDIT_COST,
        "message": "已开始 AI 智能选品",
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


@router.post("/products/{product_id}/generate-derived")
def generate_derived(product_id: int, db: Session = Depends(get_db)):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在")
    try:
        prepare_product_for_derivation(db, product)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"商品翻译/分族失败：{exc}") from exc
    result = generate_derivatives_for_products(db, [product])
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.source_product_id == product_id)
        .order_by(DerivedProductRecommendation.weighted_score.desc(), DerivedProductRecommendation.id.desc())
    ).all()
    return {
        "ok": True,
        "model_used": bool(result.get("model_used")),
        "count": len(items),
        "items": [derived_to_dict(item) for item in items],
        "generation_result": result,
    }


def run_product_full_pipeline(product_id: int, task_id: int) -> None:
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
            generation = generate_derivatives_for_products(db, [product], task_id=task_id)
            if not int(generation.get("generated_count") or 0):
                raise RuntimeError(str(generation.get("error") or "衍生品生成失败"))
            derived_ids = list(
                db.scalars(
                    select(DerivedProductRecommendation.id)
                    .where(DerivedProductRecommendation.source_product_id == product_id)
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
def generate_full_task(product_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在")
    task = create_task(db, task_type="product_full_pipeline", task_name="单品完整衍生", trigger_source="product_click", total_count=2, input_snapshot={"product_id": product_id})
    background_tasks.add_task(run_product_full_pipeline, product_id, task.id)
    return {"ok": True, "task_id": task.id, "status": task.status, "progress": 0}


@router.get("/product-full-tasks/{task_id}")
def product_full_task_status(task_id: int, db: Session = Depends(get_db)):
    task = db.get(TaskExecution, task_id)
    if not task or task.task_type != "product_full_pipeline":
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        result = json.loads(task.result_snapshot or "{}")
    except ValueError:
        result = {}
    progress = 100 if task.status == "success" else int(result.get("progress") or 0)
    return {"id": task.id, "status": task.status, "progress": progress, "stage": result.get("stage", ""), "message": result.get("message", ""), "error_message": task.error_message, "processed_count": task.processed_count, "success_count": task.success_count, "failed_count": task.failed_count}
