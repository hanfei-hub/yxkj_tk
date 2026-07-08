from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.entities import (
    DailyRecommendation,
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    ModelConfig,
    SelectionAttribute,
    TeacherReviewRecord,
    ThirdPartyConfig,
    User,
)


def fmt_dt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "status": user.status,
        "last_login_at": fmt_dt(user.last_login_at),
        "created_at": fmt_dt(user.created_at),
        "updated_at": fmt_dt(user.updated_at),
    }


def model_config_to_dict(item: ModelConfig) -> dict[str, Any]:
    return {
        "id": item.id,
        "config_name": item.config_name,
        "provider": item.provider,
        "base_url": item.base_url,
        "has_api_key": bool(item.api_key_encrypted),
        "model_name": item.model_name,
        "temperature": item.temperature,
        "max_tokens": item.max_tokens,
        "is_default": item.is_default,
        "status": item.status,
        "remark": item.remark,
    }


def third_party_config_to_dict(item: ThirdPartyConfig) -> dict[str, Any]:
    return {
        "id": item.id,
        "config_name": item.config_name,
        "service_type": item.service_type,
        "api_base_url": item.api_base_url,
        "db_host": item.db_host,
        "db_port": item.db_port,
        "db_name": item.db_name,
        "db_user": item.db_user,
        "status": item.status,
        "remark": item.remark,
    }


def attribute_to_dict(item: SelectionAttribute) -> dict[str, Any]:
    return {
        "id": item.id,
        "attribute_name": item.attribute_name,
        "attribute_code": item.attribute_code,
        "attribute_type": item.attribute_type,
        "description": item.description,
        "default_weight": item.default_weight,
        "current_weight": item.current_weight,
        "is_system": item.is_system,
        "status": item.status,
        "created_by": item.created_by,
    }


def product_to_dict(item: FmProduct) -> dict[str, Any]:
    derived = item.derived_products or []
    pending = [child for child in derived if child.review_status == "pending"]
    return {
        "id": item.id,
        "fm_product_id": item.fm_product_id,
        "title": item.title,
        "image_url": item.image_url,
        "price": item.price,
        "currency": item.currency,
        "sales_count": item.sales_count,
        "rank_no": item.rank_no,
        "category": item.category,
        "comment_count": item.comment_count,
        "data_date": item.data_date,
        "derived_count": len(derived),
        "pending_count": len(pending),
        "reviewed_count": len(derived) - len(pending),
    }


def attribute_score_to_dict(item: DerivedProductAttributeScore) -> dict[str, Any]:
    return {
        "attribute_id": item.attribute_id,
        "attribute_name": item.attribute.attribute_name if item.attribute else "",
        "ai_score": item.ai_score,
        "ai_reason": item.ai_reason,
        "teacher_result": item.teacher_result,
        "teacher_comment": item.teacher_comment,
    }


def derived_to_dict(item: DerivedProductRecommendation) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_product_id": item.source_product_id,
        "derived_title": item.derived_title,
        "derived_description": item.derived_description,
        "recommendation_reason": item.recommendation_reason,
        "target_audience": item.target_audience,
        "usage_scene": item.usage_scene,
        "suggested_price_min": item.suggested_price_min,
        "suggested_price_max": item.suggested_price_max,
        "search_keywords": item.search_keywords,
        "risk_notes": item.risk_notes,
        "ai_score": item.ai_score,
        "weighted_score": item.weighted_score,
        "supplier_search_status": item.supplier_search_status,
        "review_status": item.review_status,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": fmt_dt(item.reviewed_at),
        "attributes": [attribute_score_to_dict(score) for score in item.attributes],
    }


def daily_to_dict(item: DailyRecommendation) -> dict[str, Any]:
    return {
        "id": item.id,
        "recommendation_date": item.recommendation_date,
        "source_product_id": item.source_product_id,
        "recommendation_id": item.recommendation_id,
        "title": item.title,
        "image_url": item.image_url,
        "price": item.price,
        "sales_count": item.sales_count,
        "reason_summary": item.reason_summary,
        "sort_order": item.sort_order,
    }


def review_to_dict(item: TeacherReviewRecord) -> dict[str, Any]:
    return {
        "id": item.id,
        "teacher_id": item.teacher_id,
        "source_product_id": item.source_product_id,
        "recommendation_id": item.recommendation_id,
        "review_result": item.review_result,
        "selected_attribute_ids": item.selected_attribute_ids,
        "review_comment": item.review_comment,
        "review_snapshot": item.review_snapshot,
        "created_at": fmt_dt(item.created_at),
    }
