from __future__ import annotations

import json
import os
import requests
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import ModelConfig, ThirdPartyConfig, VideoProject
from app.services.video_generation_service import (
    create_video_task,
    delete_asset,
    delete_project,
    generate_script,
    get_project,
    list_projects,
    project_to_dict,
    refresh_video_task,
    save_asset,
    save_script_frames,
)


router = APIRouter(prefix="/api/video", tags=["video"], dependencies=[Depends(require_role("admin", "teacher", "student"))])
DEFAULT_BUMING_VIDEO_MODEL_ALLOWLIST = "seedance-2-0-ecom-special,ecom-allpurpose-video,seedance-2-0-promo"
DEFAULT_BUMING_VIDEO_MODEL = "seedance-2-0-ecom-special"
BUMING_VIDEO_MODEL_LABELS = {
    "seedance-2-0-ecom-special": "即梦特价 · 电商特价",
    "ecom-allpurpose-video": "即梦特价 · 自研-全能视频2.0",
    "seedance-2-0-promo": "即梦特价 · 特价按秒",
}


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


class BumingSyncPayload(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


def default_buming_params(model: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    mode_options: list[str] = []
    upload_params: list[str] = []
    for param in model.get("params") or []:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        if not name:
            continue
        if str(param.get("type") or "").strip() == "upload" or name in {"images", "videos", "audios"}:
            upload_params.append(name)
            continue
        options = param.get("options") if isinstance(param.get("options"), list) else []
        if name == "mode":
            mode_options = [str(option.get("value") or "") for option in options if isinstance(option, dict) and option.get("value")]
        if "default" in param:
            defaults[name] = param.get("default")
            continue
        default_option = next((option for option in options if isinstance(option, dict) and option.get("is_default")), None)
        if isinstance(default_option, dict):
            defaults[name] = default_option.get("value")
            continue
        if options and isinstance(options[0], dict):
            defaults[name] = options[0].get("value")
    if mode_options:
        defaults["_mode_options"] = mode_options
    if upload_params:
        defaults["_upload_params"] = upload_params
    return defaults


def allowed_buming_video_models(payload_model: str = "") -> set[str]:
    raw = payload_model.strip() or os.getenv("BUMING_VIDEO_MODEL_ALLOWLIST", "").strip()
    if not raw:
        raw = DEFAULT_BUMING_VIDEO_MODEL_ALLOWLIST
    return {item.strip() for item in raw.split(",") if item.strip()}


def buming_video_model_label(model: dict[str, Any], model_name: str) -> str:
    return BUMING_VIDEO_MODEL_LABELS.get(model_name) or str(model.get("display_name") or model_name)


@router.get("/projects")
def projects(db: Session = Depends(get_db), user: dict = Depends(require_role("admin", "teacher", "student"))):
    return list_projects(db, user)


@router.get("/models")
def video_models(db: Session = Depends(get_db), user: dict = Depends(require_role("admin"))):
    items = (
        db.query(ModelConfig)
        .filter(
            ModelConfig.status == 1,
            ModelConfig.provider == "buming_ai",
            ModelConfig.model_type == "video_generation",
            ModelConfig.model_name != "",
        )
        .order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "label": item.config_name or "视频模型",
            "value": f"buming:{item.model_name}",
        }
        for item in items
    ]


@router.post("/models/buming/sync")
def sync_buming_video_models(
    payload: BumingSyncPayload,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    config = (
        db.query(ThirdPartyConfig)
        .filter(
            ThirdPartyConfig.status == 1,
            ThirdPartyConfig.service_type.in_(["buming_ai", "buming", "tokengo", "token_go"]),
            ThirdPartyConfig.access_key_encrypted != "",
        )
        .order_by(ThirdPartyConfig.id.desc())
        .first()
    )
    api_key = payload.api_key.strip() or (config.access_key_encrypted if config else "")
    if not api_key:
        raise HTTPException(status_code=400, detail="请先在第三方 API 中启用 buming_ai，并填写 Access Key。")
    base_url = (payload.base_url.strip() or (config.api_base_url if config else "") or "https://buming.token6688.com").rstrip("/")
    api_base = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    try:
        response = requests.get(
            f"{api_base}/skills/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Models API returned non-JSON response.") from exc
    models = data.get("models") if isinstance(data, dict) else []
    if not isinstance(models, list):
        models = []
    allowed_models = allowed_buming_video_models(payload.model_name)
    default_model = os.getenv("BUMING_VIDEO_DEFAULT_MODEL", DEFAULT_BUMING_VIDEO_MODEL).strip()
    if default_model not in allowed_models:
        default_model = sorted(allowed_models)[0] if allowed_models else ""
    synced = 0
    enabled = 0
    for model in models:
        if not isinstance(model, dict) or str(model.get("type") or "") != "video":
            continue
        model_name = str(model.get("name") or "").strip()
        if not model_name:
            continue
        is_allowed = model_name in allowed_models
        defaults = default_buming_params(model)
        item = (
            db.query(ModelConfig)
            .filter(
                ModelConfig.provider == "buming_ai",
                ModelConfig.model_type == "video_generation",
                ModelConfig.model_name == model_name,
            )
            .first()
        )
        if not item:
            item = ModelConfig(
                config_name=buming_video_model_label(model, model_name),
                provider="buming_ai",
                model_type="video_generation",
                model_name=model_name,
                status=1 if is_allowed else 0,
                is_default=1 if is_allowed and model_name == default_model else 0,
                remark=json.dumps(defaults, ensure_ascii=False),
            )
            db.add(item)
            synced += 1
        else:
            item.config_name = buming_video_model_label(model, model_name)
            item.status = 1 if is_allowed else 0
            item.is_default = 1 if is_allowed and model_name == default_model else 0
            if not str(item.remark or "").strip() or str(item.remark or "").strip() == "{}":
                item.remark = json.dumps(defaults, ensure_ascii=False)
        if is_allowed:
            enabled += 1
    db.commit()
    return {
        "ok": True,
        "synced": synced,
        "enabled": enabled,
        "allowed_models": sorted(allowed_models),
        "total_video_models": len([m for m in models if isinstance(m, dict) and str(m.get("type") or "") == "video"]),
    }


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


@router.delete("/projects/{project_id}")
def remove_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    delete_project(db, project)
    return {"ok": True, "project_id": project_id}


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


@router.delete("/projects/{project_id}/assets/{asset_id}")
def remove_asset(
    project_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin", "teacher", "student")),
):
    try:
        project = get_project(db, project_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        delete_asset(db, project, asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
