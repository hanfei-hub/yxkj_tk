from __future__ import annotations

import os
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import VideoProject
from app.services.video_generation_service import (
    create_video_task,
    generate_script,
    get_project,
    list_projects,
    project_to_dict,
    refresh_video_task,
    save_asset,
    save_script_frames,
)


router = APIRouter(prefix="/api/video", tags=["video"], dependencies=[Depends(require_role("admin", "teacher", "student"))])


class VideoProjectPayload(BaseModel):
    title: str = ""
    target_market: str = "日本"
    video_language: str = "日语"
    product_details: str = ""


class VideoScriptPayload(BaseModel):
    script_text: str = ""
    storyboard: list[dict[str, Any]] = []


class VideoAssetPayload(BaseModel):
    role: str = ""
    description: str = ""
    is_primary: int = 0


class VideoTaskPayload(BaseModel):
    generation_mode: str = "text_to_video"
    model_name: str = "Doubao-Seedance-2.0-Fast"


@router.get("/projects")
def projects(db: Session = Depends(get_db), user: dict = Depends(require_role("admin", "teacher", "student"))):
    return list_projects(db, user)


@router.post("/projects")
def create_project(
    payload: VideoProjectPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    project = VideoProject(
        user_id=int(user.get("id") or 0),
        title=payload.title or "未命名视频项目",
        target_market=payload.target_market,
        video_language=payload.video_language,
        product_details=payload.product_details,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_dict(db, project)


@router.put("/projects/{project_id}")
def update_project(
    project_id: int,
    payload: VideoProjectPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    project.title = payload.title or project.title
    project.target_market = payload.target_market
    project.video_language = payload.video_language
    project.product_details = payload.product_details
    db.commit()
    db.refresh(project)
    return project_to_dict(db, project)


@router.post("/projects/{project_id}/assets")
def upload_asset(
    project_id: int,
    role: str = Form(""),
    description: str = Form(""),
    is_primary: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    suffix = os.path.splitext(file.filename or "")[1] or ".png"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(temp_path, "wb") as target:
            target.write(file.file.read())
        asset = save_asset(db, project, temp_path, role, description, bool(is_primary))
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    return project_to_dict(db, project) | {"uploaded_asset_id": asset.id}


@router.put("/projects/{project_id}/assets/{asset_id}")
def update_asset(
    project_id: int,
    asset_id: int,
    payload: VideoAssetPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from app.models.entities import VideoAsset

    asset = db.get(VideoAsset, asset_id)
    if not asset or asset.project_id != project.id:
        raise HTTPException(status_code=404, detail="Video asset not found.")
    asset.role = payload.role
    asset.description = payload.description
    asset.is_primary = int(payload.is_primary or 0)
    db.commit()
    db.refresh(project)
    return project_to_dict(db, project)


@router.post("/projects/{project_id}/script/generate")
def generate_project_script(
    project_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
        return generate_script(db, project)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/projects/{project_id}/script")
def save_project_script(
    project_id: int,
    payload: VideoScriptPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    project.script_text = payload.script_text
    project.status = "script_ready"
    save_script_frames(db, project, payload.storyboard)
    db.commit()
    db.refresh(project)
    return project_to_dict(db, project)


@router.post("/projects/{project_id}/tasks")
def submit_video_task(
    project_id: int,
    payload: VideoTaskPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
        return create_video_task(db, project, int(user.get("id") or 0), payload.generation_mode, payload.model_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/tasks/{task_id}/refresh")
def refresh_task(
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
        return refresh_video_task(db, project, task_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
