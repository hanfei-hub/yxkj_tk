from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import SessionLocal, get_db
from app.models.entities import CreditTransaction, User
from app.services.auto_publish_service import (
    create_1688_batch_publish_task,
    create_1688_publish_task,
    list_miaoshou_shop_options,
    get_task_result,
    get_latest_result,
    list_history,
    save_miaoshou_picture_space_storage_state,
    mark_task_runtime_failure,
    run_1688_publish_task,
)


router = APIRouter(
    prefix="/api/auto-publish",
    tags=["auto-publish"],
    dependencies=[Depends(require_role("admin", "teacher", "student"))],
)


def user_id_and_role(user: dict) -> tuple[int, str]:
    return int(user.get("id") or 0), str(user.get("role") or "")


def consume_publish_credits(db: Session, user_id: int, count: int) -> int:
    count = max(1, int(count))
    db_user = db.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    balance = int(db_user.credit_balance or 0)
    if balance < count:
        raise HTTPException(status_code=400, detail=f"积分不足，本次上架 {count} 条商品需要 {count} 积分")
    db_user.credit_balance = balance - count
    db.add(CreditTransaction(
        user_id=user_id,
        transaction_type="consume",
        credits=-count,
        balance_after=db_user.credit_balance,
        source="auto_publish",
        remark=f"自动上架 {count} 条商品",
    ))
    db.commit()
    return int(db_user.credit_balance)


def refund_publish_credits(db: Session, user_id: int, count: int) -> None:
    db_user = db.get(User, user_id)
    if not db_user:
        return
    db_user.credit_balance = int(db_user.credit_balance or 0) + int(count)
    db.add(CreditTransaction(
        user_id=user_id,
        transaction_type="refund",
        credits=int(count),
        balance_after=db_user.credit_balance,
        source="auto_publish",
        remark="自动上架任务创建失败，退回积分",
    ))
    db.commit()


def run_auto_publish_task_in_background(task_id: str) -> None:
    db = SessionLocal()
    try:
        run_1688_publish_task(db, task_id)
    except Exception as exc:
        mark_task_runtime_failure(task_id, str(exc))
    finally:
        db.close()


class AutoPublish1688ItemRequest(BaseModel):
    offer_url: str
    package_weight_g: float = 500
    package_length_cm: float = 10
    package_width_cm: float = 10
    package_height_cm: float = 40
    profit_rule: str = ""
    pricing_currency: str = "CNY"


class AutoPublish1688Request(BaseModel):
    offer_url: str
    publish_count: int = 1
    target_channel: str = "TikTok Shop Japan"
    target_language: str = "ja"
    target_site: str = "JP"
    target_shop_id: int | None = None
    miaoshou_app_key: str = ""
    miaoshou_app_secret: str = ""
    miaoshou_api_base_url: str = ""
    enable_image_translation: bool = True
    enable_image_removal: bool = True
    enable_title_optimization: bool = True
    enable_sku_optimization: bool = True
    enable_description_optimization: bool = True
    remove_logo: bool = True
    remove_transparent_text: bool = True
    remove_text: bool = False
    remove_psoriasis: bool = True
    package_weight_g: float = 500
    package_length_cm: float = 10
    package_width_cm: float = 10
    package_height_cm: float = 40
    profit_rule: str = ""
    pricing_currency: str = "CNY"
    dry_run: bool = False


class AutoPublish1688BatchRequest(BaseModel):
    offer_urls: list[str]
    items: list[AutoPublish1688ItemRequest] = Field(default_factory=list)
    publish_count: int = 1
    target_channel: str = "TikTok Shop Japan"
    target_language: str = "ja"
    target_site: str = "JP"
    target_shop_id: int | None = None
    miaoshou_app_key: str = ""
    miaoshou_app_secret: str = ""
    miaoshou_api_base_url: str = ""
    enable_image_translation: bool = True
    enable_image_removal: bool = True
    enable_title_optimization: bool = True
    enable_sku_optimization: bool = True
    enable_description_optimization: bool = True
    remove_logo: bool = True
    remove_transparent_text: bool = True
    remove_text: bool = False
    remove_psoriasis: bool = True
    profit_rule: str = ""
    pricing_currency: str = "CNY"
    dry_run: bool = False


class MiaoshouShopListRequest(BaseModel):
    target_site: str = "JP"
    miaoshou_app_key: str = ""
    miaoshou_app_secret: str = ""
    miaoshou_api_base_url: str = ""


class MiaoshouReauthorizeRequest(BaseModel):
    storage_state: dict[str, Any]


@router.get("/latest")
def latest(user: dict = Depends(require_role("admin", "teacher", "student"))):
    user_id, role = user_id_and_role(user)
    return get_latest_result(user_id=user_id, role=role)


@router.get("/history")
def history(user: dict = Depends(require_role("admin", "teacher", "student"))):
    user_id, role = user_id_and_role(user)
    return list_history(user_id=user_id, role=role)


@router.post("/miaoshou/shop-list")
def miaoshou_shop_list(
    payload: MiaoshouShopListRequest,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    try:
        return list_miaoshou_shop_options(db, payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/miaoshou/reauthorize-picture-space")
def miaoshou_reauthorize_picture_space(
    payload: MiaoshouReauthorizeRequest,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    try:
        return save_miaoshou_picture_space_storage_state(db, payload.storage_state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
def get_auto_publish_task(task_id: str, user: dict = Depends(require_role("admin", "teacher", "student"))):
    user_id, role = user_id_and_role(user)
    result = get_task_result(task_id, user_id=user_id, role=role)
    if not result:
        raise HTTPException(status_code=404, detail="Auto publish task not found.")
    return result


@router.post("/tasks/{task_id}/run")
def run_auto_publish_task(
    task_id: str,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    user_id, role = user_id_and_role(user)
    if not get_task_result(task_id, user_id=user_id, role=role):
        raise HTTPException(status_code=404, detail="Auto publish task not found.")
    try:
        return run_1688_publish_task(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto publish task failed: {exc}") from exc


@router.post("/tasks/{task_id}/run-async")
def run_auto_publish_task_async(
    task_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    user_id, role = user_id_and_role(user)
    existing = get_task_result(task_id, user_id=user_id, role=role)
    if not existing:
        raise HTTPException(status_code=404, detail="Auto publish task not found.")
    background_tasks.add_task(run_auto_publish_task_in_background, task_id)
    return existing | {
        "status": "running",
        "message": "自动上架任务已进入后台执行，桌面端会继续刷新进度。",
        "progress": {
            "stage": "fetch",
            "current": 0,
            "total": len(existing.get("offer_urls") or [existing.get("offer_url")]),
            "message": "后台任务已启动",
            "percent": 1,
        },
    }


@router.post("/1688/tasks")
def create_1688_task(
    payload: AutoPublish1688Request,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    user_id = int(user.get("id") or 0)
    credit_cost = 1
    balance = consume_publish_credits(db, user_id, credit_cost)
    try:
        return create_1688_publish_task(db, payload.model_dump(), user_id=user_id) | {
            "credit_cost": credit_cost,
            "credit_balance": balance,
        }
    except ValueError as exc:
        refund_publish_credits(db, user_id, credit_cost)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        refund_publish_credits(db, user_id, credit_cost)
        raise HTTPException(status_code=500, detail=f"Auto publish task creation failed: {exc}") from exc


@router.post("/1688/batch-tasks")
def create_1688_batch_task(
    payload: AutoPublish1688BatchRequest,
    user: dict = Depends(require_role("admin", "teacher", "student")),
    db: Session = Depends(get_db),
):
    user_id = int(user.get("id") or 0)
    raw_items = payload.items if payload.items else [AutoPublish1688ItemRequest(offer_url=url) for url in payload.offer_urls]
    credit_cost = max(1, len({str(item.offer_url).strip() for item in raw_items if str(item.offer_url).strip()}))
    balance = consume_publish_credits(db, user_id, credit_cost)
    try:
        return create_1688_batch_publish_task(db, payload.model_dump(), user_id=user_id) | {
            "credit_cost": credit_cost,
            "credit_balance": balance,
        }
    except ValueError as exc:
        refund_publish_credits(db, user_id, credit_cost)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        refund_publish_credits(db, user_id, credit_cost)
        raise HTTPException(status_code=500, detail=f"Auto publish batch task creation failed: {exc}") from exc
