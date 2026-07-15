from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.services.auto_publish_service import (
    create_1688_publish_task,
    create_task,
    get_task_result,
    get_latest_result,
    list_history,
    list_publish_candidates,
    run_1688_publish_task,
    run_task,
)


router = APIRouter(
    prefix="/api/auto-publish",
    tags=["auto-publish"],
    dependencies=[Depends(require_role("admin", "teacher"))],
)


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
    erp_url: str = "https://erp.91miaoshou.com/?ac=1og270"
    dry_run: bool = False
    image_mode: str = "fast"
    miaoshou_username: str = ""
    miaoshou_password: str = ""


@router.get("/candidates")
def candidates(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return list_publish_candidates(db, limit=limit)


@router.get("/latest")
def latest():
    return get_latest_result()


@router.get("/history")
def history():
    return list_history()


@router.get("/tasks/{task_id}")
def get_auto_publish_task(task_id: str):
    result = get_task_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="自动上架任务不存在。")
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
def run_auto_publish_task(task_id: str, db: Session = Depends(get_db)):
    try:
        return run_1688_publish_task(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
