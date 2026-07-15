from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.core.security import hash_password
from app.models.entities import ModelConfig, SelectionAttribute, TeacherReviewRecord, ThirdPartyConfig, User, UserSearchRecommendation
from app.services.serializers import (
    attribute_to_dict,
    model_config_to_dict,
    third_party_config_to_dict,
    user_to_dict,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


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
    is_default: int = 0
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
    status: int = 1
    remark: str = ""


class AttributeCreate(BaseModel):
    attribute_name: str
    attribute_code: str | None = None
    attribute_type: str = "other"
    description: str = ""
    default_weight: float = 1.0
    status: int = 1


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
    if payload.is_default:
        for item in db.scalars(select(ModelConfig).where(ModelConfig.model_type == payload.model_type)).all():
            item.is_default = 0
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
    if payload.is_default:
        for existing in db.scalars(
            select(ModelConfig).where(ModelConfig.id != config_id, ModelConfig.model_type == payload.model_type)
        ).all():
            existing.is_default = 0
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


@router.post("/model-configs/{config_id}/default")
def set_default_model(config_id: int, db: Session = Depends(get_db)):
    item = db.get(ModelConfig, config_id)
    if not item:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    for existing in db.scalars(select(ModelConfig).where(ModelConfig.model_type == item.model_type)).all():
        existing.is_default = 1 if existing.id == config_id else 0
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
    for key, value in payload.model_dump().items():
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
