from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import (
    AiPromptTemplate,
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    TaskExecution,
)
from app.services.ai_model_service import (
    MODEL_TYPE_GENERAL,
    ModelCallError,
    chat_completion,
    extract_json_object,
    get_model_config,
)
from app.services.product_family_service import active_dimensions, save_dimension_reports, weights_for_prompt
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.system_settings_service import get_setting_int


PROMPT_CODE = "fastmoss_jp_derivation_v1"

PROMPT_CONTENT = """你是TikTok日本站跨境专业选品分析师，基于给你的选品维度权重百分比，分析出相关衍生品10个，要求每个衍生品给出维度分析信息。
分析规则：
1. 根据日区限制规则选品，不能违反以下规则：
【日本】物流禁运/禁止进出口商品清单及他法令限制要求：
https://support.oceanengine.com/support/content/144690?spaceId=235
日本地区禁售禁运规则：
https://support.oceanengine.com/support/content/8457220354?mappingType=1&spaceId=235&timestamp=1765871495844
日本禁运案例：
https://support.oceanengine.com/support/content/189021?mappingType=2&spaceId=235&timestamp=1767585663232

[维度权重信息]

2. 输出的业务结果：
根据当前启用的维度列表输出完整分析报告，每个维度包含【判定等级】+【客观分析内容】。
[维度列表]

补充要求：
1. 每个原商品必须输出10个相关衍生品方向。
2. 所有输出内容必须使用简体中文。
3. 衍生品名称要适合后续在1688按关键词找货。
4. 只基于传入的商品名称、商品图片URL和维度权重信息分析；没有充足依据时标注“无充足依据，仅作参考线索”。
5. 输出必须是纯JSON，禁止输出markdown、解释或多余文字。"""

OUTPUT_SCHEMA = {
    "items": [
        {
            "source_product_id": 0,
            "derived_title": "中文衍生品名称",
            "derived_description": "中文衍生品说明",
            "recommendation_reason": "中文推荐理由",
            "target_audience": "中文目标人群",
            "usage_scene": "中文使用场景",
            "suggested_price_min": 0,
            "suggested_price_max": 0,
            "risk_notes": "中文风险提示",
            "ai_score": 0,
            "weighted_score": 0,
            "analysis_report": {
                "dimension_1": {"dimension_name": "使用场景", "rating_level": "", "analysis_content": ""},
                "dimension_2": {"dimension_name": "商品周期性", "rating_level": "", "analysis_content": ""},
                "dimension_3": {"dimension_name": "目标群体", "rating_level": "", "analysis_content": ""},
                "dimension_4": {"dimension_name": "短视频流量种草适配能力", "rating_level": "", "analysis_content": ""},
                "dimension_5": {"dimension_name": "日本市场偏好", "rating_level": "", "analysis_content": ""},
                "dimension_6": {"dimension_name": "是否属于新奇特商品", "rating_level": "", "analysis_content": ""},
                "dimension_7": {"dimension_name": "复购属性", "rating_level": "", "analysis_content": ""},
                "dimension_8": {"dimension_name": "竞品属性", "rating_level": "", "analysis_content": ""},
            },
            "source_search_keywords": ["1688中文主关键词", "中文拓展关键词"],
            "match_tags": ["中文类目标签", "中文功能标签", "中文场景标签"],
        }
    ]
}


def build_output_schema(db: Session) -> dict[str, Any]:
    schema = json.loads(json.dumps(OUTPUT_SCHEMA, ensure_ascii=False))
    schema["items"][0]["analysis_report"] = {
        code: {
            "dimension_name": name,
            "rating_level": "",
            "analysis_content": "",
        }
        for code, name in active_dimensions(db)
    }
    return schema


def ensure_selection_prompt(db: Session) -> AiPromptTemplate:
    item = db.scalar(select(AiPromptTemplate).where(AiPromptTemplate.prompt_code == PROMPT_CODE))
    if item:
        return item
    raise RuntimeError(f"未找到启用的选品提示词：{PROMPT_CODE}")


def product_payload(products: list[FmProduct]) -> list[dict[str, Any]]:
    return [
        {
            "source_product_id": item.id,
            "title": item.title,
            "image_url": item.image_url,
        }
        for item in products
    ]


def format_weight_prompt(weights: dict[str, str]) -> str:
    lines = ["选品维度权重百分比："]
    for name, percent in weights.items():
        lines.append(f"{name}：{percent}")
    return "\n".join(lines)


def format_dimension_prompt(db: Session) -> str:
    return "\n".join(
        f"维度{index}：{name}（字段：{code}）"
        for index, (code, name) in enumerate(active_dimensions(db), start=1)
    )


def normalize_items(raw: Any, product_ids: set[int]) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw_items = raw.get("items") or []
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raw_items = []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        try:
            source_product_id = int(raw_item.get("source_product_id"))
        except (TypeError, ValueError):
            continue
        if source_product_id not in product_ids:
            continue
        raw_item["source_product_id"] = source_product_id
        items.append(raw_item)
    return items


def build_derivation_prompt(db: Session, products: list[FmProduct], prompt_template: AiPromptTemplate, derivative_count: int) -> str:
    current_product = products[0] if products else None
    weight_info = weights_for_prompt(db, current_product.family_id if current_product else None)
    prompt_content = prompt_template.prompt_content.replace(
        "[维度权重信息]",
        format_weight_prompt(weight_info),
    ).replace("[维度列表]", format_dimension_prompt(db)).replace("10个", f"{derivative_count}个")
    return (
        f"{prompt_content}\n\n"
        f"输出 JSON 结构必须严格等于：{prompt_template.output_schema}\n\n"
        "请只基于下面传入的商品名称、商品图片URL和维度权重信息，"
        f"为每个 source_product_id 输出 {derivative_count} 个最值得进一步找货的中文衍生品方向。\n"
        "维度权重越高，表示老师历史审核越认可；维度权重越低，表示更容易被拒绝。"
        "生成衍生品时请有意识偏向高权重维度，并谨慎处理低权重维度。\n"
        "每个衍生品必须包含当前维度列表的完整 analysis_report，并补充 source_search_keywords 和 match_tags，"
        "用于后续 1688/API 找货匹配。\n"
        f"商品名称和图片：{json.dumps(product_payload(products), ensure_ascii=False)}"
    )

def generate_derivatives_for_products(db: Session, products: list[FmProduct], task_id: int | None = None) -> dict[str, Any]:
    if not products:
        return {"model_used": False, "generated_count": 0, "error": ""}
    prompt_template = ensure_selection_prompt(db)
    derivative_count = get_setting_int(db, "derivatives_per_product")
    model_config = get_model_config(db, MODEL_TYPE_GENERAL)
    if not model_config:
        return {"model_used": False, "generated_count": 0, "error": "no_model_config"}

    answer = ""
    try:
        answer = chat_completion(
            db,
            [
                {
                    "role": "system",
                    "content": "你是 TikTok 日本站跨境专业选品分析师。只输出合法 JSON，所有字段内容必须使用简体中文。",
                },
                {"role": "user", "content": build_derivation_prompt(db, products, prompt_template, derivative_count)},
            ],
            model_type=MODEL_TYPE_GENERAL,
            task_id=task_id,
            temperature=0.2,
            max_tokens=12000,
        )
        try:
            parsed = extract_json_object(answer)
        except ModelCallError as exc:
            return {
                "model_used": True,
                "generated_count": 0,
                "error": f"json_parse_failed: {exc}; response_tail={answer[-800:]}",
            }
        items = normalize_items(parsed, {item.id for item in products})
    except ModelCallError as exc:
        return {"model_used": True, "generated_count": 0, "error": str(exc)}

    if not items:
        return {"model_used": True, "generated_count": 0, "error": "empty_model_items"}

    product_map = {item.id: item for item in products}
    source_ids = list(product_map)
    pending_ids = list(
        db.scalars(
            select(DerivedProductRecommendation.id).where(
                DerivedProductRecommendation.source_product_id.in_(source_ids),
                DerivedProductRecommendation.review_status == "pending",
            )
        ).all()
    )
    if pending_ids:
        db.execute(delete(DerivedProductAttributeScore).where(DerivedProductAttributeScore.recommendation_id.in_(pending_ids)))
        db.execute(delete(DerivedProductRecommendation).where(DerivedProductRecommendation.id.in_(pending_ids)))
        db.flush()

    saved_count = 0
    for item in items:
        source_product = product_map.get(int(item["source_product_id"]))
        if not source_product:
            continue
        keywords = item.get("source_search_keywords") or []
        match_tags = item.get("match_tags") or []
        analysis_report = item.get("analysis_report") or {}
        derived_title = str(item.get("derived_title") or source_product.title or "未命名衍生品")
        derived = DerivedProductRecommendation(
            family_id=source_product.family_id,
            source_product_id=source_product.id,
            derived_title=derived_title[:255],
            derived_description=str(item.get("derived_description") or ""),
            recommendation_reason=str(item.get("recommendation_reason") or ""),
            target_audience=str(item.get("target_audience") or "")[:255],
            usage_scene=str(item.get("usage_scene") or "")[:255],
            suggested_price_min=item.get("suggested_price_min"),
            suggested_price_max=item.get("suggested_price_max"),
            search_keywords=str(keywords[0] if isinstance(keywords, list) and keywords else derived_title)[:512],
            risk_notes=str(item.get("risk_notes") or ""),
            analysis_report=json.dumps(analysis_report, ensure_ascii=False),
            source_search_keywords=json.dumps(keywords, ensure_ascii=False),
            match_tags=json.dumps(match_tags, ensure_ascii=False),
            prompt_template_id=prompt_template.id,
            model_used=model_config.model_name,
            ai_score=float(item.get("ai_score") or 0),
            weighted_score=float(item.get("weighted_score") or item.get("ai_score") or 0),
            supplier_search_status="not_searched",
            supplier_next_page=1,
            supplier_searched_count=0,
            review_status="pending",
        )
        db.add(derived)
        db.flush()
        save_dimension_reports(db, recommendation=derived, analysis_report=analysis_report)
        saved_count += 1
    db.commit()
    return {"model_used": True, "generated_count": saved_count, "error": ""}


def generate_derivatives_for_product_ids(product_ids: list[int], task_id: int | None = None) -> dict[str, Any]:
    total_generated = 0
    errors: list[str] = []
    task_result_id: int | None = task_id
    with SessionLocal() as db:
        task = db.get(TaskExecution, task_id) if task_id else None
        if not task:
            task = create_task(
                db,
                task_type="derivation_generate",
                task_name="衍生品生成",
                trigger_source="background",
                total_count=len(product_ids),
                input_snapshot={"product_ids": product_ids},
            )
        task_result_id = int(task.id)
        shared_task_id = task_result_id
        started = start_timer()
        def process_one(product_id: int) -> dict[str, Any]:
            with SessionLocal() as worker_db:
                product = worker_db.get(FmProduct, product_id)
                if not product:
                    return {"product_id": product_id, "generated_count": 0, "error": "product_not_found"}
                result = generate_derivatives_for_products(worker_db, [product], task_id=shared_task_id)
                return {
                    "product_id": product_id,
                    "generated_count": int(result.get("generated_count") or 0),
                    "error": str(result.get("error") or ""),
                }

        # Ten source products are processed concurrently as one batch. Each
        # worker owns its DB session, while chat_completion distributes calls
        # across all active models of the requested type.
        for batch_start in range(0, len(product_ids), 10):
            batch = product_ids[batch_start : batch_start + 10]
            with ThreadPoolExecutor(max_workers=len(batch), thread_name_prefix="derive") as executor:
                futures = [executor.submit(process_one, product_id) for product_id in batch]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"product_id": 0, "generated_count": 0, "error": str(exc)}
                    total_generated += result["generated_count"]
                    if result["error"]:
                        errors.append(f"{result['product_id']}: {result['error']}")
            # Persist visible progress after every ten-product batch.
            db.expire_all()
            task.processed_count = min(batch_start + len(batch), len(product_ids))
            task.success_count = task.processed_count - len(errors)
            task.failed_count = len(errors)
            db.commit()
        finish_task(
            db,
            task,
            status="failed" if errors else "success",
            processed_count=len(product_ids),
            success_count=len(product_ids) - len(errors),
            failed_count=len(errors),
            elapsed_ms_value=elapsed_ms(started),
            result_snapshot={"generated_count": total_generated, "errors": errors},
            error_message="; ".join(errors[:5]),
        )
    return {"generated_count": total_generated, "errors": errors, "task_id": task_result_id}

