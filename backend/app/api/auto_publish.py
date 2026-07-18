from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import SessionLocal, get_db
from app.services.auto_publish_service import (
    create_1688_batch_publish_task,
    create_1688_publish_task,
    create_task,
    get_task_result,
    get_latest_result,
    list_history,
    list_publish_candidates,
    mark_task_runtime_failure,
    run_1688_publish_task,
    run_task,
)


router = APIRouter(
    prefix="/api/auto-publish",
    tags=["auto-publish"],
    dependencies=[Depends(require_role("admin", "teacher"))],
)


def user_id_and_role(user: dict) -> tuple[int, str]:
    return int(user.get("id") or 0), str(user.get("role") or "")


def run_auto_publish_task_in_background(task_id: str) -> None:
    db = SessionLocal()
    try:
        run_1688_publish_task(db, task_id)
    except Exception as exc:
        mark_task_runtime_failure(task_id, str(exc))
    finally:
        db.close()


class AutoPublishTaskRequest(BaseModel):
    derived_id: int
    publish_count: int = 1
    target_channel: str = "TikTok Shop Japan"
    erp_url: str = "https://erp.91miaoshou.com/?ac=1og270"
    dry_run: bool = True


class AutoPublish1688Request(BaseModel):
    offer_url: str
    publish_count: int = 1
    target_channel: str = "TikTok Shop Japan"
    target_language: str = "ja"
    erp_url: str = "https://erp.91miaoshou.com/?ac=1og270"
    dry_run: bool = False
    miaoshou_username: str = ""
    miaoshou_password: str = ""


class AutoPublish1688BatchRequest(BaseModel):
    offer_urls: list[str]
    publish_count: int = 1
    target_channel: str = "TikTok Shop Japan"
    target_language: str = "ja"
    erp_url: str = "https://erp.91miaoshou.com/?ac=1og270"
    dry_run: bool = False
    miaoshou_username: str = ""
    miaoshou_password: str = ""


@router.get("/candidates")
def candidates(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return list_publish_candidates(db, limit=limit)


@router.get("/latest")
def latest(user: dict = Depends(require_role("admin", "teacher"))):
    user_id, role = user_id_and_role(user)
    return get_latest_result(user_id=user_id, role=role)


@router.get("/history")
def history(user: dict = Depends(require_role("admin", "teacher"))):
    user_id, role = user_id_and_role(user)
    return list_history(user_id=user_id, role=role)


@router.get("/tasks/{task_id}")
def get_auto_publish_task(task_id: str, user: dict = Depends(require_role("admin", "teacher"))):
    user_id, role = user_id_and_role(user)
    result = get_task_result(task_id, user_id=user_id, role=role)
    if not result:
        raise HTTPException(status_code=404, detail="Auto publish task not found.")
    return result


@router.post("/tasks")
def create_auto_publish_task(
    payload: AutoPublishTaskRequest,
    user: dict = Depends(require_role("admin", "teacher")),
    db: Session = Depends(get_db),
):
    try:
        return create_task(db, payload.model_dump(), user_id=user.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/run")
def run_auto_publish_task(
    task_id: str,
    user: dict = Depends(require_role("admin", "teacher")),
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
    user: dict = Depends(require_role("admin", "teacher")),
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
    user: dict = Depends(require_role("admin", "teacher")),
    db: Session = Depends(get_db),
):
    try:
        return create_1688_publish_task(db, payload.model_dump(), user_id=user.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto publish task creation failed: {exc}") from exc


@router.post("/1688/batch-tasks")
def create_1688_batch_task(
    payload: AutoPublish1688BatchRequest,
    user: dict = Depends(require_role("admin", "teacher")),
    db: Session = Depends(get_db),
):
    try:
        return create_1688_batch_publish_task(db, payload.model_dump(), user_id=user.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto publish batch task creation failed: {exc}") from exc
