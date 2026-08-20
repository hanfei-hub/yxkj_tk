from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import CreditTransaction, FavoriteProduct, User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    transactions = db.scalars(select(CreditTransaction)).all()
    recharged = sum(max(0, int(item.credits or 0)) for item in transactions if item.transaction_type == "recharge")
    consumed = sum(abs(int(item.credits or 0)) for item in transactions if item.transaction_type == "consume")
    refunded = sum(max(0, int(item.credits or 0)) for item in transactions if item.transaction_type in {"refund", "rollback"})
    users = db.scalars(select(User)).all()
    favorites = db.scalars(select(FavoriteProduct)).all()
    category_counts: dict[str, int] = defaultdict(int)
    for item in favorites:
        category_counts[str(item.category or "未分类").strip() or "未分类"] += 1
    return {"credits": {"remaining": sum(int(item.credit_balance or 0) for item in users), "recharged": recharged, "consumed": consumed, "refunded": refunded}, "categories": [{"name": name, "count": count} for name, count in sorted(category_counts.items(), key=lambda pair: (-pair[1], pair[0]))], "favorite_count": len(favorites), "scope": "all_users"}
