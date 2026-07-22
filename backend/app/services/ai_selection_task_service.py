from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import AiPromptTemplate, TaskExecution, User, UserSearchRecommendation
from app.services.ai_model_service import (
    MODEL_TYPE_PRODUCT_VISION,
    ModelCallError,
    chat_completion,
    extract_json_object,
)
from app.services.execution_log_service import create_task, elapsed_ms, finish_task, start_timer
from app.services.supplier_1688_service import Supplier1688Error, auto_match_1688_for_search_result


PROMPT_CODE = "ai_selection_from_user_v1"
PROMPT_CONTENT = """你是TikTok日本站跨境专业选品分析师，根据给出的选品逻辑，选出10个商品，要求每个商品给出维度分析信息
选品逻辑：[用户对话框内容]
分析规则：
1,根据日区限制规则选品，不能违反以下规则
【日本】物流禁运/禁止进出口商品清单及他法令限制要求：https://support.oceanengine.com/support/content/144690?spaceId=235
日本地区禁售禁运规则：
https://support.oceanengine.com/support/content/8457220354?mappingType=1&spaceId=235&timestamp=1765871495844
日本禁运案例
https://support.oceanengine.com/support/content/189021?mappingType=2&spaceId=235&timestamp=1767585663232

2， 输出的业务结果：
八个维度完整分析报告，每个维度包含【判定等级】+【客观分析内容】
如下：
维度1：使用场景
维度2：商品周期性
维度3：目标群体
维度4：短视频流量种草适配能力
维度5：日本市场偏好
维度6：是否属于新奇特商品
维度7：复购属性
维度8：竞品属性"""

OUTPUT_SCHEMA = {
    "items": [
        {
            "title": "商品名称",
            "reason_summary": "推荐理由摘要",
            "price": 0,
            "sales_count": 0,
            "image_url": "",
            "analysis_report": {
                "使用场景": {"level": "判定等级", "content": "客观分析内容"},
                "商品周期性": {"level": "判定等级", "content": "客观分析内容"},
                "目标群体": {"level": "判定等级", "content": "客观分析内容"},
                "短视频流量种草适配能力": {"level": "判定等级", "content": "客观分析内容"},
                "日本市场偏好": {"level": "判定等级", "content": "客观分析内容"},
                "是否属于新奇特商品": {"level": "判定等级", "content": "客观分析内容"},
                "复购属性": {"level": "判定等级", "content": "客观分析内容"},
                "竞品属性": {"level": "判定等级", "content": "客观分析内容"},
            },
        }
    ]
}


def ensure_ai_selection_prompt(db: Session) -> AiPromptTemplate:
    item = db.scalar(select(AiPromptTemplate).where(AiPromptTemplate.prompt_code == PROMPT_CODE))
    schema_text = json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
    if item:
        item.prompt_name = "AI 智能选品搜索任务"
        item.prompt_content = PROMPT_CONTENT
        item.output_schema = schema_text
        item.status = 1
        item.remark = "前端智能选品搜索框提交后，根据用户输入生成 10 个用户私有搜索结果。"
        db.flush()
        return item
    item = AiPromptTemplate(
        prompt_code=PROMPT_CODE,
        prompt_name="AI 智能选品搜索任务",
        prompt_content=PROMPT_CONTENT,
        output_schema=schema_text,
        status=1,
        remark="前端智能选品搜索框提交后，根据用户输入生成 10 个用户私有搜索结果。",
    )
    db.add(item)
    db.flush()
    return item


def build_prompt(template: AiPromptTemplate, user_message: str) -> str:
    content = template.prompt_content.replace("[用户对话框内容]", user_message.strip())
    return (
        f"{content}\n\n"
        "请严格输出纯 JSON，不要输出 markdown、解释或多余文字。\n"
        "如果没有真实可访问的商品图片 URL，image_url 必须输出空字符串，不要编造 example.com 或占位图片。\n"
        f"JSON 结构必须符合：{template.output_schema}"
    )


def normalize_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw_items = raw.get("items") or raw.get("products") or []
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raw_items = []

    items: list[dict[str, Any]] = []
    for raw_item in raw_items[:10]:
        if not isinstance(raw_item, dict):
            continue
        title = str(raw_item.get("title") or raw_item.get("product_name") or "").strip()
        if not title:
            continue
        report = raw_item.get("analysis_report") or raw_item.get("dimensions") or {}
        reason = str(raw_item.get("reason_summary") or raw_item.get("recommendation_reason") or "")
        if not reason and isinstance(report, dict):
            reason = json.dumps(report, ensure_ascii=False)[:600]
        image_url = str(
            raw_item.get("image_url")
            or raw_item.get("image")
            or raw_item.get("imageUrl")
            or raw_item.get("product_image_url")
            or raw_item.get("product_image")
            or raw_item.get("pic_url")
            or raw_item.get("picUrl")
            or raw_item.get("main_image")
            or raw_item.get("mainImage")
            or ""
        ).strip()
        if "example.com" in image_url.lower():
            image_url = ""
        items.append(
            {
                "title": title[:255],
                "image_url": image_url,
                "price": float(raw_item.get("price") or 0),
                "sales_count": int(float(raw_item.get("sales_count") or 0)),
                "reason_summary": reason,
                "analysis_report": report,
            }
        )
    return items


def update_task_progress(db: Session, task: TaskExecution, *, processed_count: int, stage: str, message: str = "") -> None:
    task.processed_count = processed_count
    task.result_snapshot = json.dumps(
        {"stage": stage, "message": message, "progress": int(processed_count * 100 / max(task.total_count or 1, 1))},
        ensure_ascii=False,
    )
    db.commit()


def save_user_search_recommendations(
    db: Session,
    *,
    user_id: int,
    task_id: int,
    search_query: str,
    items: list[dict[str, Any]],
) -> None:
    cutoff = datetime.utcnow() - timedelta(days=7)
    db.execute(delete(UserSearchRecommendation).where(UserSearchRecommendation.created_at < cutoff))
    now = datetime.utcnow()
    for index, item in enumerate(items, start=1):
        db.add(
            UserSearchRecommendation(
                user_id=user_id,
                task_id=task_id,
                search_query=search_query,
                title=item["title"],
                image_url=item["image_url"],
                price=item["price"],
                sales_count=item["sales_count"],
                reason_summary=item["reason_summary"],
                analysis_report=json.dumps(item.get("analysis_report") or {}, ensure_ascii=False),
                sort_order=index,
                created_at=now,
            )
        )
    db.commit()


def start_ai_selection_task(db: Session, user_message: str, user_id: int) -> TaskExecution:
    return create_task(
        db,
        task_type="ai_selection",
        task_name="AI 智能选品搜索",
        trigger_source="student_dialog",
        total_count=4,
        input_snapshot={"message": user_message, "user_id": user_id},
    )


def run_ai_selection_task(task_id: int, user_message: str, user_id: int, credit_cost: int = 0) -> None:
    with SessionLocal() as db:
        task = db.get(TaskExecution, task_id)
        if not task:
            return
        started = start_timer()
        try:
            update_task_progress(db, task, processed_count=1, stage="prepare_prompt", message="正在组装选品话术")
            template = ensure_ai_selection_prompt(db)
            db.commit()
            prompt = build_prompt(template, user_message)

            update_task_progress(db, task, processed_count=2, stage="model_generating", message="大模型正在生成 10 个商品")
            answer = chat_completion(
                db,
                [
                    {"role": "system", "content": "你是 TikTok 日本站跨境专业选品分析师，只输出合法 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                model_type=MODEL_TYPE_PRODUCT_VISION,
                task_id=task.id,
                temperature=0.2,
                max_tokens=12000,
            )

            update_task_progress(db, task, processed_count=3, stage="saving_results", message="正在保存本次搜索结果")
            items = normalize_items(extract_json_object(answer))
            if not items:
                raise ModelCallError("大模型未返回可入库的商品列表")
            save_user_search_recommendations(db, user_id=user_id, task_id=task.id, search_query=user_message, items=items)

            update_task_progress(db, task, processed_count=3, stage="supplier_matching", message="正在为搜索结果匹配 1688 货源")
            search_results = db.scalars(
                select(UserSearchRecommendation)
                .where(UserSearchRecommendation.task_id == task.id, UserSearchRecommendation.user_id == user_id)
                .order_by(UserSearchRecommendation.sort_order.asc(), UserSearchRecommendation.id.asc())
            ).all()
            supplier_errors: list[str] = []
            for index, search_result in enumerate(search_results, start=1):
                try:
                    auto_match_1688_for_search_result(db, search_result, task_id=task.id, all_pages=True)
                except Supplier1688Error as exc:
                    search_result.supplier_search_status = "failed"
                    search_result.supplier_match_report = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    db.commit()
                    supplier_errors.append(f"{search_result.id}: {exc}")
                update_task_progress(
                    db,
                    task,
                    processed_count=3,
                    stage="supplier_matching",
                    message=f"1688 匹配进度 {index}/{len(search_results)}",
                )

            finish_task(
                db,
                task,
                status="success",
                processed_count=4,
                success_count=len(items),
                failed_count=0,
                elapsed_ms_value=elapsed_ms(started),
                result_snapshot={"stage": "finished", "progress": 100, "generated_count": len(items), "supplier_errors": supplier_errors},
            )
        except Exception as exc:
            if credit_cost > 0:
                user = db.get(User, user_id)
                if user:
                    user.credit_balance = int(user.credit_balance or 0) + int(credit_cost)
                    db.flush()
            finish_task(
                db,
                task,
                status="failed",
                processed_count=max(task.processed_count, 1),
                success_count=0,
                failed_count=1,
                elapsed_ms_value=elapsed_ms(started),
                result_snapshot={
                    "stage": "failed",
                    "progress": max(5, int(task.processed_count * 100 / 4)),
                    "credit_refunded": credit_cost,
                },
                error_message=str(exc),
            )


def user_search_result_to_dict(item: UserSearchRecommendation) -> dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "task_id": item.task_id,
        "search_query": item.search_query,
        "title": item.title,
        "image_url": item.image_url,
        "price": item.price,
        "sales_count": item.sales_count,
        "reason_summary": item.reason_summary,
        "analysis_report": item.analysis_report,
        "supplier_search_status": item.supplier_search_status,
        "supplier_next_page": item.supplier_next_page,
        "supplier_searched_count": item.supplier_searched_count,
        "supplier_product_id": item.supplier_product_id,
        "supplier_title": item.supplier_title,
        "supplier_image_url": item.supplier_image_url,
        "supplier_price": item.supplier_price,
        "supplier_sales_count": item.supplier_sales_count,
        "supplier_shop_name": item.supplier_shop_name,
        "supplier_source_url": item.supplier_source_url,
        "supplier_match_score": item.supplier_match_score,
        "supplier_match_report": item.supplier_match_report,
        "sort_order": item.sort_order,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
