from datetime import datetime, timedelta, timezone
import os
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext


SECRET_KEY = os.getenv("TK_SELECTION_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-only-secret-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
