from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DerivedProductAttributeScore, DerivedProductRecommendation, FmProduct, TaskExecution, User, UserSearchRecommendation
from app.services.ai_selection_task_service import run_ai_selection_task, start_ai_selection_task, user_search_result_to_dict
from app.services.selection_derivation_service import generate_derivatives_for_products
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
    items = db.scalars(
        select(UserSearchRecommendation)
        .where(UserSearchRecommendation.user_id == user_id)
        .order_by(UserSearchRecommendation.sort_order, UserSearchRecommendation.id)
        .limit(10)
    ).all()
    return [user_search_result_to_dict(item) for item in items]


@router.post("/products/{product_id}/generate-derived")
def generate_derived(product_id: int, db: Session = Depends(get_db)):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在")
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
