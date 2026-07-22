from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import User
from app.services.serializers import user_to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


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
