import os
import json
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
import requests

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import ThirdPartyConfig, User
from app.services.serializers import user_to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])
SMS_CODES: dict[str, tuple[str, datetime]] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    real_name: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or user.status != 1 or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), {"role": user.role})
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    password = payload.password.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="账号至少需要 3 个字符")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="账号已存在")
    user = User(
        username=username,
        password_hash=hash_password(password),
        real_name=payload.real_name.strip() or username,
        role="student",
        status=1,
        credit_balance=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), {"role": user.role})
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


class SmsSendRequest(BaseModel):
    phone: str


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


@router.post("/sms/send")
def send_sms_code(payload: SmsSendRequest, db: Session = Depends(get_db)):
    phone = payload.phone.strip()
    if not phone or len(phone) < 6:
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    code = f"{secrets.randbelow(1000000):06d}"
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "aliyun_sms", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    access_key_id = str((config.access_key_encrypted if config else "") or os.getenv("ALIYUN_SMS_ACCESS_KEY_ID", "")).strip()
    access_key_secret = str((config.secret_key_encrypted if config else "") or os.getenv("ALIYUN_SMS_ACCESS_KEY_SECRET", "")).strip()
    sign_name = str((config.sign_name if config else "") or os.getenv("ALIYUN_SMS_SIGN_NAME", "")).strip()
    template_code = str((config.template_code if config else "") or os.getenv("ALIYUN_SMS_TEMPLATE_CODE", "")).strip()
    if not all((access_key_id, access_key_secret, sign_name, template_code)):
        raise HTTPException(status_code=503, detail="阿里云短信尚未配置完整，请配置 AccessKey、短信签名和模板 Code")
    try:
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525 import models as dysms_models
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            endpoint="dysmsapi.aliyuncs.com",
        )
        client = Client(config)
        request = dysms_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=sign_name,
            template_code=template_code,
            template_param=json.dumps({"code": code}, ensure_ascii=False),
        )
        response = client.send_sms(request)
        body = getattr(response, "body", None)
        response_code = str(getattr(body, "code", "") or "")
        if response_code != "OK":
            message = str(getattr(body, "message", "") or "阿里云短信发送失败")
            raise HTTPException(status_code=502, detail=f"阿里云短信发送失败：{message}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"阿里云短信调用失败：{type(exc).__name__}: {exc}") from exc
    SMS_CODES[phone] = (code, datetime.utcnow() + timedelta(minutes=5))
    return {"ok": True, "message": "验证码已发送"}


@router.post("/sms/login")
def sms_login(payload: SmsLoginRequest, db: Session = Depends(get_db)):
    phone = payload.phone.strip()
    record = SMS_CODES.get(phone)
    if not record or record[0] != payload.code.strip() or record[1] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    SMS_CODES.pop(phone, None)
    username = f"phone:{phone}"
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        user = User(username=username, password_hash=hash_password(secrets.token_urlsafe(24)), real_name=f"用户{phone[-4:]}", role="student", status=1, credit_balance=0)
        db.add(user)
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), {"role": user.role})
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


@router.get("/wechat/login-url")
def wechat_login_url():
    app_id = os.getenv("WECHAT_APP_ID", "").strip()
    redirect_uri = os.getenv("WECHAT_REDIRECT_URI", "").strip()
    if not app_id or not redirect_uri:
        raise HTTPException(status_code=503, detail="微信登录尚未配置 WECHAT_APP_ID 和 WECHAT_REDIRECT_URI")
    state = secrets.token_urlsafe(18)
    url = (
        "https://open.weixin.qq.com/connect/qrconnect?"
        f"appid={app_id}&redirect_uri={requests.utils.quote(redirect_uri, safe='')}&response_type=code&scope=snsapi_login&state={state}#wechat_redirect"
    )
    return {"ok": True, "login_url": url, "state": state}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="新密码至少需要 6 位。")
    db_user = db.get(User, int(user["id"]))
    if not db_user or not verify_password(payload.old_password, db_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确。")
    db_user.password_hash = hash_password(payload.new_password.strip())
    db.commit()
    return {"ok": True, "message": "密码修改成功，请使用新密码登录。"}


@router.post("/logout")
def logout():
    return {"ok": True}
