import time
import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import BASE_DIR, get_db
from app.core.security import hash_password
from app.models.entities import AiPromptConstant, AppRelease, DerivedProductAttributeScore, ModelConfig, SelectionAttribute, SystemSetting, TeacherReviewRecord, ThirdPartyConfig, User, UserSearchRecommendation
from app.services.serializers import (
    attribute_to_dict,
    prompt_constant_to_dict,
    model_config_to_dict,
    system_setting_to_dict,
    third_party_config_to_dict,
    user_to_dict,
)
from app.services.system_settings_service import ensure_system_settings
from app.services.ai_model_service import ModelCallError, chat_completion

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])

RELEASE_DIR = BASE_DIR / "runtime" / "releases"
RELEASE_DIR.mkdir(parents=True, exist_ok=True)


class UserCreate(BaseModel):
    username: str
    password: str = "123456"
    real_name: str
    role: str


class UserUpdate(BaseModel):
    real_name: str
    role: str
    status: int = 1


class ResetPasswordRequest(BaseModel):
    password: str = "123456"


class StatusRequest(BaseModel):
    status: int


class CreditRechargeRequest(BaseModel):
    credits: int
    remark: str = ""


class ModelConfigPayload(BaseModel):
    config_name: str
    provider: str = "custom"
    model_type: str = "general"
    base_url: str = ""
    api_key_encrypted: str = ""
    model_name: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    status: int = 1
    remark: str = ""


class ThirdPartyConfigPayload(BaseModel):
    config_name: str
    service_type: str = "custom_api"
    api_base_url: str = ""
    access_key_encrypted: str = ""
    secret_key_encrypted: str = ""
    db_host: str = ""
    db_port: int | None = None
    db_name: str = ""
    db_user: str = ""
    db_password_encrypted: str = ""
    sign_name: str = ""
    template_code: str = ""
    status: int = 1
    remark: str = ""


class AttributeCreate(BaseModel):
    attribute_name: str
    attribute_code: str | None = None
    attribute_type: str = "other"
    description: str = ""
    default_weight: float = 1.0
    status: int = 1


class PromptConstantPayload(BaseModel):
    constant_key: str
    constant_name: str
    constant_content: str = ""
    status: int = 1
    remark: str = ""


class SystemSettingsPayload(BaseModel):
    values: dict[str, str]


def release_to_dict(item: AppRelease) -> dict[str, Any]:
    return {
        "id": item.id,
        "version": item.version,
        "filename": item.filename,
        "download_url": item.download_url,
        "release_notes": item.release_notes,
        "sha256": item.sha256,
        "force_update": bool(item.force_update),
        "status": item.status,
        "uploaded_by": item.uploaded_by,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/app-releases")
def list_app_releases(db: Session = Depends(get_db)):
    items = db.scalars(select(AppRelease).order_by(AppRelease.created_at.desc(), AppRelease.id.desc())).all()
    return [release_to_dict(item) for item in items]


@router.post("/app-releases/upload")
def upload_app_release(
    version: str = Form(...),
    release_notes: str = Form(""),
    force_update: int = Form(0),
    package: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    normalized_version = version.strip().lstrip("vV")
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}", normalized_version):
        raise HTTPException(status_code=400, detail="版本号格式应为 1.0.1")
    original_name = Path(package.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".exe", ".zip"}:
        raise HTTPException(status_code=400, detail="只支持上传 .exe 或 .zip 安装包")
    release_dir = RELEASE_DIR
    stored_name = f"tk-selection-{normalized_version}-{uuid.uuid4().hex[:10]}{suffix}"
    stored_path = release_dir / stored_name
    digest = hashlib.sha256()
    try:
        with stored_path.open("wb") as output:
            while chunk := package.file.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
    except OSError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"保存安装包失败：{exc}") from exc
    finally:
        package.file.close()

    old = db.scalar(select(AppRelease).where(AppRelease.version == normalized_version))
    if old:
        Path(old.storage_path).unlink(missing_ok=True)
        db.delete(old)
        db.flush()
    db.query(AppRelease).update({AppRelease.status: 0}, synchronize_session=False)
    public_base = os.getenv("TK_PUBLIC_BASE_URL", "http://120.26.207.89:8000").rstrip("/")
    item = AppRelease(
        version=normalized_version,
        filename=original_name or stored_name,
        storage_path=str(stored_path),
        download_url=f"{public_base}/static/releases/{stored_name}",
        release_notes=release_notes.strip(),
        sha256=digest.hexdigest(),
        force_update=1 if int(force_update or 0) else 0,
        status=1,
        uploaded_by=int(current_user.get("id") or 0) or None,
        published_at=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return release_to_dict(item)


@router.patch("/app-releases/{release_id}/publish")
def publish_app_release(release_id: int, db: Session = Depends(get_db)):
    item = db.get(AppRelease, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="版本不存在")
    db.query(AppRelease).update({AppRelease.status: 0}, synchronize_session=False)
    item.status = 1
    item.published_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return release_to_dict(item)


@router.delete("/app-releases/{release_id}")
def delete_app_release(release_id: int, db: Session = Depends(get_db)):
    item = db.get(AppRelease, release_id)
    if not item:
        raise HTTPException(status_code=404, detail="版本不存在")
    Path(item.storage_path).unlink(missing_ok=True)
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": release_id}


class ModelTestPayload(BaseModel):
    model_config_id: int
    text: str = ""
    image_url: str = ""


@router.post("/model-test")
def test_model(payload: ModelTestPayload, db: Session = Depends(get_db)):
    config = db.get(ModelConfig, payload.model_config_id)
    if not config:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    if not config.base_url or not config.api_key_encrypted or not config.model_name:
        raise HTTPException(status_code=400, detail="模型配置缺少 Base URL、API Key 或模型名称")
    content: list[dict[str, Any]] = []
    if payload.text.strip():
        content.append({"type": "text", "text": payload.text.strip()})
    if payload.image_url.strip():
        content.append({"type": "image_url", "image_url": {"url": payload.image_url.strip()}})
    if not content:
        raise HTTPException(status_code=400, detail="请输入测试文本或图片")
    started = time.perf_counter()
    try:
        answer = chat_completion(
            db,
            [{"role": "user", "content": content}],
            model_type=config.model_type,
            config_id=config.id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        return {
            "ok": True,
            "model_config_id": config.id,
            "model_name": config.model_name,
            "provider": config.provider,
            "model_type": config.model_type,
            "elapsed_ms": int(round((time.perf_counter() - started) * 1000)),
            "answer": answer,
        }
    except ModelCallError as exc:
        return {
            "ok": False,
            "model_config_id": config.id,
            "model_name": config.model_name,
            "provider": config.provider,
            "model_type": config.model_type,
            "elapsed_ms": int(round((time.perf_counter() - started) * 1000)),
            "error": str(exc),
        }


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [user_to_dict(user) for user in users]


@router.post("/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        role=payload.role,
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.real_name = payload.real_name
    user.role = payload.role
    user.status = payload.status
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.status = payload.status
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.post("/users/{user_id}/credits/recharge")
def recharge_user_credits(user_id: int, payload: CreditRechargeRequest, db: Session = Depends(get_db)):
    if payload.credits <= 0:
        raise HTTPException(status_code=400, detail="充值积分必须大于0")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.credit_balance = int(user.credit_balance or 0) + int(payload.credits)
    db.commit()
    db.refresh(user)
    return {"ok": True, "credits_added": payload.credits, "user": user_to_dict(user)}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(payload.password)
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if user_id == int(current_user.get("id") or 0):
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    review_exists = db.scalar(select(TeacherReviewRecord.id).where(TeacherReviewRecord.teacher_id == user_id).limit(1))
    if review_exists:
        raise HTTPException(status_code=400, detail="该用户已有审核记录，不能直接删除，可先禁用账号")
    db.execute(delete(UserSearchRecommendation).where(UserSearchRecommendation.user_id == user_id))
    db.delete(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="该用户存在关联数据，不能直接删除，可先禁用账号") from exc
    return {"ok": True, "deleted_id": user_id}


@router.get("/model-configs")
def list_model_configs(db: Session = Depends(get_db)):
    items = db.scalars(select(ModelConfig).order_by(ModelConfig.id)).all()
    return [model_config_to_dict(item) for item in items]


@router.post("/model-configs")
def create_model_config(payload: ModelConfigPayload, db: Session = Depends(get_db)):
    item = ModelConfig(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return model_config_to_dict(item)


@router.put("/model-configs/{config_id}")
def update_model_config(config_id: int, payload: ModelConfigPayload, db: Session = Depends(get_db)):
    item = db.get(ModelConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return model_config_to_dict(item)


@router.patch("/model-configs/{config_id}/status")
def update_model_status(config_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    item = db.get(ModelConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return model_config_to_dict(item)


@router.delete("/model-configs/{config_id}")
def delete_model_config(config_id: int, db: Session = Depends(get_db)):
    item = db.get(ModelConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": config_id}


@router.get("/third-party-configs")
def list_third_party_configs(db: Session = Depends(get_db)):
    items = db.scalars(select(ThirdPartyConfig).order_by(ThirdPartyConfig.id)).all()
    return [third_party_config_to_dict(item) for item in items]


@router.get("/system-settings")
def list_system_settings(db: Session = Depends(get_db)):
    ensure_system_settings(db)
    db.commit()
    items = db.scalars(select(SystemSetting).order_by(SystemSetting.id)).all()
    return [system_setting_to_dict(item) for item in items]


@router.put("/system-settings")
def update_system_settings(payload: SystemSettingsPayload, db: Session = Depends(get_db)):
    ensure_system_settings(db)
    updated = []
    for key, value in payload.values.items():
        item = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
        if not item:
            raise HTTPException(status_code=400, detail=f"未知系统参数：{key}")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"参数 {item.setting_name} 必须是数字") from exc
        if item.min_value is not None and numeric_value < item.min_value:
            raise HTTPException(status_code=400, detail=f"参数 {item.setting_name} 不能小于 {item.min_value:g}")
        if item.max_value is not None and numeric_value > item.max_value:
            raise HTTPException(status_code=400, detail=f"参数 {item.setting_name} 不能大于 {item.max_value:g}")
        item.setting_value = str(value).strip()
        updated.append(item)
    db.commit()
    return [system_setting_to_dict(item) for item in updated]


@router.post("/third-party-configs")
def create_third_party_config(payload: ThirdPartyConfigPayload, db: Session = Depends(get_db)):
    item = ThirdPartyConfig(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return third_party_config_to_dict(item)


@router.put("/third-party-configs/{config_id}")
def update_third_party_config(config_id: int, payload: ThirdPartyConfigPayload, db: Session = Depends(get_db)):
    item = db.get(ThirdPartyConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="第三方配置不存在")
    values = payload.model_dump()
    for key in ("access_key_encrypted", "secret_key_encrypted", "db_password_encrypted"):
        if not values.get(key):
            values[key] = getattr(item, key)
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return third_party_config_to_dict(item)


@router.patch("/third-party-configs/{config_id}/status")
def update_third_party_status(config_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    item = db.get(ThirdPartyConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="第三方配置不存在")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return third_party_config_to_dict(item)


@router.delete("/third-party-configs/{config_id}")
def delete_third_party_config(config_id: int, db: Session = Depends(get_db)):
    item = db.get(ThirdPartyConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="第三方配置不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": config_id}


@router.get("/selection-attributes")
def list_selection_attributes(db: Session = Depends(get_db)):
    items = db.scalars(select(SelectionAttribute).order_by(SelectionAttribute.id)).all()
    return [attribute_to_dict(item) for item in items]


@router.post("/selection-attributes")
def create_selection_attribute(
    payload: AttributeCreate,
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    attribute = SelectionAttribute(
        attribute_name=payload.attribute_name,
        attribute_code=payload.attribute_code or payload.attribute_name.lower().replace(" ", "_"),
        attribute_type=payload.attribute_type,
        description=payload.description,
        default_weight=payload.default_weight,
        current_weight=payload.default_weight,
        is_system=0,
        status=payload.status,
        created_by=user["id"],
    )
    db.add(attribute)
    db.commit()
    db.refresh(attribute)
    return attribute_to_dict(attribute)


@router.put("/selection-attributes/{attribute_id}")
def update_selection_attribute(attribute_id: int, payload: AttributeCreate, db: Session = Depends(get_db)):
    attribute = db.get(SelectionAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="属性不存在")
    attribute.attribute_name = payload.attribute_name
    attribute.attribute_code = payload.attribute_code or payload.attribute_name.lower().replace(" ", "_")
    attribute.attribute_type = payload.attribute_type
    attribute.description = payload.description
    attribute.default_weight = payload.default_weight
    attribute.current_weight = payload.default_weight
    attribute.status = payload.status
    db.commit()
    db.refresh(attribute)
    return attribute_to_dict(attribute)


@router.patch("/selection-attributes/{attribute_id}/status")
def update_attribute_status(attribute_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    attribute = db.get(SelectionAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="属性不存在")
    attribute.status = payload.status
    db.commit()
    db.refresh(attribute)
    return attribute_to_dict(attribute)


@router.delete("/selection-attributes/{attribute_id}")
def delete_selection_attribute(attribute_id: int, db: Session = Depends(get_db)):
    attribute = db.get(SelectionAttribute, attribute_id)
    if not attribute:
        raise HTTPException(status_code=404, detail="属性不存在")
    score_exists = db.scalar(select(DerivedProductAttributeScore.id).where(DerivedProductAttributeScore.attribute_id == attribute_id).limit(1))
    if score_exists:
        raise HTTPException(status_code=400, detail="该属性已有历史审核评分，不能直接删除，请先禁用属性。")
    db.delete(attribute)
    db.commit()
    return {"ok": True, "deleted_id": attribute_id}


@router.get("/prompt-constants")
def list_prompt_constants(db: Session = Depends(get_db)):
    items = db.scalars(select(AiPromptConstant).order_by(AiPromptConstant.id.asc())).all()
    return [prompt_constant_to_dict(item) for item in items]


@router.post("/prompt-constants")
def create_prompt_constant(payload: PromptConstantPayload, db: Session = Depends(get_db)):
    key = payload.constant_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="常量编码不能为空")
    if db.scalar(select(AiPromptConstant).where(AiPromptConstant.constant_key == key)):
        raise HTTPException(status_code=400, detail="常量编码已存在")
    item = AiPromptConstant(
        constant_key=key,
        constant_name=payload.constant_name.strip() or key,
        constant_content=payload.constant_content,
        status=payload.status,
        remark=payload.remark,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return prompt_constant_to_dict(item)


@router.put("/prompt-constants/{constant_id}")
def update_prompt_constant(constant_id: int, payload: PromptConstantPayload, db: Session = Depends(get_db)):
    item = db.get(AiPromptConstant, constant_id)
    if not item:
        raise HTTPException(status_code=404, detail="常量不存在")
    item.constant_key = payload.constant_key.strip() or item.constant_key
    item.constant_name = payload.constant_name.strip() or item.constant_key
    item.constant_content = payload.constant_content
    item.status = payload.status
    item.remark = payload.remark
    db.commit()
    db.refresh(item)
    return prompt_constant_to_dict(item)


@router.patch("/prompt-constants/{constant_id}/status")
def update_prompt_constant_status(constant_id: int, payload: StatusRequest, db: Session = Depends(get_db)):
    item = db.get(AiPromptConstant, constant_id)
    if not item:
        raise HTTPException(status_code=404, detail="常量不存在")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return prompt_constant_to_dict(item)


@router.delete("/prompt-constants/{constant_id}")
def delete_prompt_constant(constant_id: int, db: Session = Depends(get_db)):
    item = db.get(AiPromptConstant, constant_id)
    if not item:
        raise HTTPException(status_code=404, detail="常量不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": constant_id}
