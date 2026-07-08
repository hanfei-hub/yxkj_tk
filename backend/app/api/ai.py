from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import DerivedProductAttributeScore, DerivedProductRecommendation
from app.services.serializers import derived_to_dict

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_role("admin", "teacher", "student"))])


class ChatSelectionRequest(BaseModel):
    message: str


@router.post("/chat-selection")
def chat_selection(payload: ChatSelectionRequest):
    return {
        "answer": (
            "基于日本区 TikTok 当前趋势，建议优先关注宠物耗材、厨房清洁小工具、"
            "桌面氛围类低客单商品。你的问题是："
            f"{payload.message}。MVP 数据库版这里仍先返回占位分析，下一阶段会接入后台配置的大模型。"
        ),
        "directions": ["宠物复购耗材", "厨房清洁场景延展", "桌面氛围配件"],
    }


@router.post("/products/{product_id}/generate-derived")
def generate_derived(product_id: int, db: Session = Depends(get_db)):
    matched = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.source_product_id == product_id)
        .order_by(DerivedProductRecommendation.weighted_score.desc())
    ).all()
    return {"ok": True, "count": len(matched), "items": [derived_to_dict(item) for item in matched]}
