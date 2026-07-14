from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import (
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    SelectionAttribute,
)
from app.services.ai_model_service import ModelCallError, chat_completion, extract_json_object
from app.services.serializers import derived_to_dict

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_role("admin", "teacher", "student"))])


class ChatSelectionRequest(BaseModel):
    message: str


def fallback_chat(message: str) -> dict[str, Any]:
    return {
        "answer": (
            "基于日本 TikTok 电商选品，建议优先看低客单、轻小件、短视频可展示、可复购或可组合销售的商品。"
            f"针对你的需求「{message}」，可以从宠物耗材、厨房清洁、桌面氛围、收纳配件和新奇特小工具里继续筛。"
        ),
        "directions": ["宠物复购耗材", "厨房清洁场景延展", "桌面氛围配件", "轻小新奇特工具"],
        "model_used": False,
    }


@router.post("/chat-selection")
def chat_selection(payload: ChatSelectionRequest, db: Session = Depends(get_db)):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空。")
    try:
        answer = chat_completion(
            db,
            [
                {
                    "role": "system",
                    "content": (
                        "你是日本 TikTok 跨境电商智能选品助手。回答要具体、可执行，"
                        "围绕价格带、目标人群、使用场景、内容传播性、物流风险和侵权风险给建议。"
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=1200,
        )
        return {"answer": answer, "directions": [], "model_used": True}
    except ModelCallError:
        return fallback_chat(message)


def product_context(product: FmProduct) -> str:
    return json.dumps(
        {
            "title": product.title,
            "category": product.category,
            "price_jpy": product.price,
            "sales_count": product.sales_count,
            "comment_count": product.comment_count,
            "data_date": product.data_date,
            "raw_data": product.raw_data[:3000] if product.raw_data else "{}",
        },
        ensure_ascii=False,
    )


def attribute_context(attributes: list[SelectionAttribute]) -> str:
    return json.dumps(
        [
            {
                "id": item.id,
                "name": item.attribute_name,
                "code": item.attribute_code,
                "type": item.attribute_type,
                "weight": item.current_weight,
                "description": item.description,
            }
            for item in attributes
        ],
        ensure_ascii=False,
    )


def fallback_derived_items(product: FmProduct, attributes: list[SelectionAttribute]) -> list[dict[str, Any]]:
    title = product.title or "原商品"
    category = product.category or "日本新品榜"
    default_attrs = attributes[:3]
    return [
        {
            "derived_title": f"{title} 配件/补充装",
            "derived_description": "围绕原商品形成加购、复购或替换耗材方向。",
            "recommendation_reason": f"原商品类目为 {category}，可优先延展同一使用场景下的配件、耗材和组合套装。",
            "target_audience": "已被原商品吸引的日本用户",
            "usage_scene": "同一使用场景下的加购和复购",
            "suggested_price_min": max(300, float(product.price or 0) * 0.2),
            "suggested_price_max": max(800, float(product.price or 0) * 0.8),
            "search_keywords": f"{title} 配件 1688",
            "risk_notes": "需确认 1688 供货稳定性、侵权风险和跨境物流体积。",
            "ai_score": 84,
            "weighted_score": 84,
            "attributes": [{"attribute_id": item.id, "ai_score": 82, "ai_reason": "本地规则生成的默认评分。"} for item in default_attrs],
        },
        {
            "derived_title": f"{title} 低价替代款",
            "derived_description": "用同类低价替代款覆盖价格敏感用户。",
            "recommendation_reason": "同一需求下测试不同价格带，适合验证转化空间。",
            "target_audience": "价格敏感型消费者",
            "usage_scene": "同类目测款和价格带覆盖",
            "suggested_price_min": max(300, float(product.price or 0) * 0.3),
            "suggested_price_max": max(1200, float(product.price or 0) * 0.9),
            "search_keywords": f"{title} 同款 平替 1688",
            "risk_notes": "注意同质化竞争和素材差异化。",
            "ai_score": 80,
            "weighted_score": 80,
            "attributes": [{"attribute_id": item.id, "ai_score": 78, "ai_reason": "本地规则生成的默认评分。"} for item in default_attrs],
        },
    ]


def normalize_generated_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw_items = raw.get("items") or raw.get("derived_products") or []
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raw_items = []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items[:5]:
        if isinstance(raw_item, dict):
            items.append(raw_item)
    return items


def generate_with_model(db: Session, product: FmProduct, attributes: list[SelectionAttribute]) -> tuple[list[dict[str, Any]], bool]:
    prompt = f"""
请基于下面的日本 TikTok 原商品和选品属性，生成 3 个可给老师审核的衍生品方向。

要求：
1. 审核对象是“衍生品方向”，不是具体 1688 商品。
2. 每个衍生品要有与原商品的关系信息，如周期性、使用场景、同属新奇特、人群匹配、价格带匹配、物流风险、侵权风险。
3. search_keywords 用于后续调用 1688 API 搜索。
4. 只返回 JSON，不要解释。

原商品：
{product_context(product)}

选品属性：
{attribute_context(attributes)}

返回格式：
{{
  "items": [
    {{
      "derived_title": "",
      "derived_description": "",
      "recommendation_reason": "",
      "target_audience": "",
      "usage_scene": "",
      "suggested_price_min": 0,
      "suggested_price_max": 0,
      "search_keywords": "",
      "risk_notes": "",
      "ai_score": 0,
      "weighted_score": 0,
      "attributes": [
        {{"attribute_id": 1, "ai_score": 0, "ai_reason": ""}}
      ]
    }}
  ]
}}
"""
    try:
        answer = chat_completion(
            db,
            [
                {"role": "system", "content": "你是跨境电商 AI 选品分析师，只输出符合要求的 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
        )
        items = normalize_generated_items(extract_json_object(answer))
        return items, True
    except ModelCallError:
        return fallback_derived_items(product, attributes), False


def save_generated_items(
    db: Session,
    product: FmProduct,
    attributes: list[SelectionAttribute],
    items: list[dict[str, Any]],
) -> list[DerivedProductRecommendation]:
    pending_ids = list(
        db.scalars(
            select(DerivedProductRecommendation.id).where(
                DerivedProductRecommendation.source_product_id == product.id,
                DerivedProductRecommendation.review_status == "pending",
            )
        ).all()
    )
    if pending_ids:
        db.execute(delete(DerivedProductAttributeScore).where(DerivedProductAttributeScore.recommendation_id.in_(pending_ids)))
        db.execute(delete(DerivedProductRecommendation).where(DerivedProductRecommendation.id.in_(pending_ids)))
        db.flush()

    attribute_ids = {item.id for item in attributes}
    saved: list[DerivedProductRecommendation] = []
    for item in items:
        derived = DerivedProductRecommendation(
            source_product_id=product.id,
            derived_title=str(item.get("derived_title") or "未命名衍生品")[:255],
            derived_description=str(item.get("derived_description") or ""),
            recommendation_reason=str(item.get("recommendation_reason") or ""),
            target_audience=str(item.get("target_audience") or "")[:255],
            usage_scene=str(item.get("usage_scene") or "")[:255],
            suggested_price_min=item.get("suggested_price_min"),
            suggested_price_max=item.get("suggested_price_max"),
            search_keywords=str(item.get("search_keywords") or item.get("derived_title") or "")[:512],
            risk_notes=str(item.get("risk_notes") or ""),
            ai_score=float(item.get("ai_score") or 0),
            weighted_score=float(item.get("weighted_score") or item.get("ai_score") or 0),
            supplier_search_status="not_searched",
            review_status="pending",
        )
        db.add(derived)
        db.flush()

        for attr in item.get("attributes") or []:
            try:
                attribute_id = int(attr.get("attribute_id"))
            except (TypeError, ValueError, AttributeError):
                continue
            if attribute_id not in attribute_ids:
                continue
            db.add(
                DerivedProductAttributeScore(
                    source_product_id=product.id,
                    recommendation_id=derived.id,
                    attribute_id=attribute_id,
                    ai_score=float(attr.get("ai_score") or 0),
                    ai_reason=str(attr.get("ai_reason") or ""),
                )
            )
        saved.append(derived)
    db.commit()
    return saved


@router.post("/products/{product_id}/generate-derived")
def generate_derived(product_id: int, db: Session = Depends(get_db)):
    product = db.get(FmProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="原商品不存在。")
    attributes = db.scalars(select(SelectionAttribute).where(SelectionAttribute.status == 1).order_by(SelectionAttribute.id)).all()
    items, model_used = generate_with_model(db, product, attributes)
    saved = save_generated_items(db, product, attributes, items)
    refreshed = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.id.in_([item.id for item in saved]))
        .order_by(DerivedProductRecommendation.weighted_score.desc())
    ).all()
    return {"ok": True, "model_used": model_used, "count": len(refreshed), "items": [derived_to_dict(item) for item in refreshed]}
