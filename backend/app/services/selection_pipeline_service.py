from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import (
    AiPromptConstant,
    FmProduct,
    Selection1688Candidate,
    SelectionDidadogProduct,
    SelectionImageSearchEntry,
    SelectionPipelineKeyword,
    SelectionPipelineTask,
    SelectionRestrictionRule,
)
from app.services.ai_model_service import MODEL_TYPE_GENERAL, ModelCallError, chat_completion, extract_json_object
from app.services.echotik_service import EchoTikError, get_product_details, search_by_image
from app.services.supplier_1688_service import Supplier1688Error, search_1688_products
from app.services.system_settings_service import ensure_system_settings, get_setting_int


PIPELINE_TASK_TYPE = "selection_pipeline_v2"
PIPELINE_STAGES = (
    "keyword_generation",
    "supplier_search",
    "price_seed_selection",
    "image_search",
    "product_detail",
    "blue_ocean_filter",
    "compliance_filter",
    "restriction_check",
    "final_selection",
)

PIPELINE_TARGETS = {
    "keywords": 50,
    "supplier_candidates": 500,
    "image_search_entries": 100,
    "didadog_ids": 600,
    "didadog_details": 600,
    "candidates": 30,
    "final_products": 10,
}


def _pipeline_limits(db: Session) -> tuple[bool, int, int, int]:
    ensure_system_settings(db)
    test_mode = get_setting_int(db, "selection_pipeline_test_mode") == 1
    keyword_limit = max(5, get_setting_int(db, "selection_pipeline_test_keywords")) if test_mode else 50
    supplier_page_size = get_setting_int(db, "selection_pipeline_test_supplier_page_size") if test_mode else 10
    seed_per_keyword = 2
    return test_mode, max(1, keyword_limit), max(1, supplier_page_size), seed_per_keyword


def _pipeline_targets(keyword_limit: int, supplier_page_size: int, seed_per_keyword: int) -> dict[str, int]:
    return {**PIPELINE_TARGETS, "keywords": keyword_limit, "supplier_candidates": keyword_limit * supplier_page_size, "image_search_entries": keyword_limit * seed_per_keyword, "didadog_ids": keyword_limit * seed_per_keyword * 6, "didadog_details": keyword_limit * seed_per_keyword * 6}


def create_selection_pipeline_task(db: Session, *, user_id: int, message: str, mode: str = "selection", source_product_id: int | None = None) -> SelectionPipelineTask:
    test_mode, keyword_limit, supplier_page_size, seed_per_keyword = _pipeline_limits(db)
    targets = _pipeline_targets(keyword_limit, supplier_page_size, seed_per_keyword)
    task = SelectionPipelineTask(
        user_id=user_id,
        pipeline_mode=mode if mode in {"selection", "derivation"} else "selection",
        source_product_id=source_product_id,
        input_message=message.strip(),
        status="pending",
        current_stage="created",
        stage_progress=0,
        result_snapshot=json.dumps(
            {"targets": targets, "stages": list(PIPELINE_STAGES), "test_mode": test_mode},
            ensure_ascii=False,
        ),
        started_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_pipeline_stage(
    db: Session,
    task: SelectionPipelineTask,
    *,
    stage: str,
    progress: int,
    status: str = "running",
    message: str = "",
    counters: dict[str, int] | None = None,
) -> None:
    if stage not in PIPELINE_STAGES and stage != "created":
        raise ValueError(f"Unknown selection pipeline stage: {stage}")
    task.status = status
    task.current_stage = stage
    task.stage_progress = max(0, min(100, int(progress)))
    if counters:
        for field, value in counters.items():
            if hasattr(task, field):
                setattr(task, field, max(0, int(value or 0)))
    snapshot: dict[str, Any]
    try:
        snapshot = json.loads(task.result_snapshot or "{}")
    except (TypeError, ValueError):
        snapshot = {}
    snapshot.update({"stage": stage, "progress": task.stage_progress, "message": message})
    if counters:
        snapshot["counters"] = counters
    task.result_snapshot = json.dumps(snapshot, ensure_ascii=False)
    db.commit()


def _constant_content(db: Session, key: str = "selection_pipeline_keywords") -> str:
    item = db.scalar(
        select(AiPromptConstant)
        .where(AiPromptConstant.constant_key == key, AiPromptConstant.status == 1)
    )
    return str(item.constant_content or "").strip() if item else ""


def _generate_report_analysis(db: Session, task: SelectionPipelineTask, candidates: list[SelectionDidadogProduct], finals: list[SelectionDidadogProduct]) -> dict[str, Any]:
    products = [
        {
            "title": item.title or item.didadog_product_id,
            "category": item.category,
            "price": item.price,
            "sales_count": item.sales_count,
            "selection_status": item.selection_status,
        }
        for item in [*candidates, *finals]
    ]
    prompt = (
        "你是日本 TikTok 跨境电商资深选品顾问。请根据本次已经完成筛选的商品生成中文市场分析报告。\n"
        "只能基于输入商品和任务需求做谨慎判断，不要虚构具体市场规模、销量、法规结论或外部数据；缺少数据时写‘需进一步验证’。\n"
        "必须严格返回 JSON，不要 Markdown，字段必须包含：\n"
        "market_intro（对象，必须包含 market_scale 市场规模、demand_trend 需求趋势、competition_landscape 竞争格局三项，每项150字以内）、\n"
        "opportunity_tracks（数组，最多3项，每项包含 track_name、opportunity、reason）、\n"
        "candidate_strategy（150字以内）、final_strategy（150字以内）、risk_advice（数组最多5条）、conclusion（100字以内）。\n"
        "蓝海原则：销量高代表成熟竞争，不等于优先推荐；重点分析低销量但有需求验证、供应链可做、差异化空间足的商品。\n"
        f"用户需求：{task.input_message}\n商品数据：{json.dumps(products, ensure_ascii=False)}"
    )
    try:
        answer = chat_completion(
            db,
            [{"role": "system", "content": "你负责生成严谨、可落地的日本市场选品报告。"}, {"role": "user", "content": prompt}],
            model_type=MODEL_TYPE_GENERAL,
            temperature=0.25,
            max_tokens=3500,
        )
        parsed = extract_json_object(answer)
        return parsed if isinstance(parsed, dict) else {"market_intro": {"market_scale": str(answer)}}
    except (ModelCallError, ValueError, TypeError) as exc:
        return {
            "market_intro": {
                "market_scale": "当前任务没有足够外部市场规模数据，需进一步验证。",
                "demand_trend": "可根据本次商品的需求关键词和 EchoTik 返回结果继续验证。",
                "competition_landscape": "本任务按低销量蓝海逻辑筛选，具体竞争强度需结合平台实时数据复核。",
            },
            "opportunity_tracks": [],
            "candidate_strategy": "优先验证候选品的供应链稳定性、成本和短视频素材表现。",
            "final_strategy": "精选品上架前完成日本法规、限售和专利风险复核。",
            "risk_advice": [f"大模型报告分析失败：{exc}"],
            "conclusion": "商品筛选结果已保存，请结合清单进行人工复核。",
        }


def _normalize_keywords(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("keywords") or raw.get("items") or raw.get("products") or []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("keyword") or item.get("product_name") or item.get("title") or item.get("name")
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:50]


def _write_error(db: Session, task: SelectionPipelineTask, message: str) -> None:
    db.rollback()
    task.status = "failed"
    task.error_message = message[:2000]
    task.finished_at = datetime.utcnow()
    db.commit()


def _set_product_reason(product: SelectionDidadogProduct, reason: str) -> None:
    product.elimination_reason = reason[:1000]
    try:
        raw = json.loads(product.raw_data or "{}")
    except (TypeError, ValueError):
        raw = {}
    raw["selection_status"] = product.selection_status
    raw["elimination_reason"] = product.elimination_reason
    product.raw_data = json.dumps(raw, ensure_ascii=False)


def _parse_compliance_result(raw: Any) -> dict[str, tuple[bool, str]]:
    values = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        return {}
    result: dict[str, tuple[bool, str]] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or item.get("id") or "").strip()
        if not product_id:
            continue
        value = item.get("compliant")
        compliant = value is True or str(value).lower() in {"true", "1", "yes", "pass", "通过", "合规"}
        result[product_id] = (compliant, str(item.get("reason") or item.get("risk_reason") or ""))
    return result


def _run_compliance_filter(db: Session, products: list[SelectionDidadogProduct]) -> None:
    if not products:
        return
    constant = db.scalar(
        select(AiPromptConstant)
        .where(AiPromptConstant.constant_key == "jp_compliance_rules", AiPromptConstant.status == 1)
    )
    names = [{"product_id": item.didadog_product_id, "title": item.title, "category": item.category} for item in products]
    prompt = (
        f"{constant.constant_content if constant else ''}\n"
        "请按照日本法规、禁运、禁售和平台限制审核以下商品。只输出 JSON。"
        "格式：{\"items\":[{\"product_id\":\"商品ID\",\"compliant\":true,\"reason\":\"原因\"}]}。"
        f"商品：{json.dumps(names, ensure_ascii=False)}"
    )
    answer = chat_completion(
        db,
        [{"role": "system", "content": "你是日本跨境商品合规审核员，只输出 JSON。"}, {"role": "user", "content": prompt}],
        model_type=MODEL_TYPE_GENERAL,
        temperature=0,
        max_tokens=6000,
    )
    decisions = _parse_compliance_result(extract_json_object(answer))
    for product in products:
        compliant, reason = decisions.get(product.didadog_product_id, (False, "模型未返回该商品的合规结论"))
        product.compliance_status = "passed" if compliant else "failed"
        if not compliant:
            product.selection_status = "compliance_failed"
            _set_product_reason(product, reason or "日本法规或禁运风险")


def _run_restriction_check(db: Session, products: list[SelectionDidadogProduct]) -> None:
    rules = list(db.scalars(select(SelectionRestrictionRule).where(SelectionRestrictionRule.status == 1, SelectionRestrictionRule.region == "JP")).all())
    for product in products:
        category = product.category.lower()
        title = product.title.lower()
        def hit(value: str, target: str) -> bool:
            return any(token and token.lower() in target for token in re.split(r"[\s,，、/|]+", value or ""))
        matches = [rule for rule in rules if hit(rule.category_keyword, category) or hit(rule.title_keyword, title)]
        if matches:
            product.restriction_status = "restricted"
            product.selection_status = "restricted"
            _set_product_reason(product, matches[0].reason or "命中日本限售规则，需要报白后运营")
        else:
            product.restriction_status = "clear"


def run_selection_pipeline(task_id: int) -> None:
    with SessionLocal() as db:
        task = db.get(SelectionPipelineTask, task_id)
        if not task:
            return
        try:
            test_mode, keyword_limit, supplier_page_size, seed_per_keyword = _pipeline_limits(db)
            derivation_mode = task.pipeline_mode == "derivation"
            source_product = db.get(FmProduct, task.source_product_id) if derivation_mode and task.source_product_id else None
            if derivation_mode and not source_product:
                raise RuntimeError("衍生任务缺少原商品")
            update_pipeline_stage(db, task, stage="keyword_generation", progress=5, message="正在让 general 大模型生成 50 个商品关键词")
            constant_key = "derivation_pipeline_keywords" if derivation_mode else "selection_pipeline_keywords"
            constant = _constant_content(db, constant_key) + "\n重要要求：所有生成的商品名称必须使用简体中文，不得输出日文、英文或其他语言；商品名称要适合后续 1688 中文关键词搜索。"
            input_message = task.input_message
            if derivation_mode and source_product:
                input_message = f"原商品：{source_product.title}\n请围绕该原商品生成可衍生的同赛道商品方向。"
            prompt = (
                f"{constant}\n\n用户需求：{input_message}\n"
                f"请只输出 JSON 数组，生成 {keyword_limit} 个{('适合该原商品衍生的' if derivation_mode else '适合 TikTok 日本站蓝海选品的')}完整商品名称。"
                "每项是一个商品名称字符串，不要编号、不要解释、不要重复。"
            )
            answer = chat_completion(
                db,
                [{"role": "system", "content": "你是日本 TikTok 跨境选品关键词专家，只输出 JSON。"}, {"role": "user", "content": prompt}],
                model_type=MODEL_TYPE_GENERAL,
                max_tokens=6000,
                temperature=0.2,
            )
            keywords = _normalize_keywords(extract_json_object(answer))
            if len(keywords) < keyword_limit:
                raise ModelCallError(f"general 大模型只返回 {len(keywords)} 个有效关键词，至少需要 {keyword_limit} 个。")
            keywords = keywords[:keyword_limit]
            for index, keyword in enumerate(keywords, start=1):
                db.add(SelectionPipelineKeyword(
                    pipeline_task_id=task.id,
                    user_id=task.user_id,
                    source_index=index,
                    keyword=keyword,
                    group_key=keyword,
                    status="generated",
                ))
            task.keyword_count = len(keywords)
            db.commit()

            keyword_rows = list(db.scalars(select(SelectionPipelineKeyword).where(SelectionPipelineKeyword.pipeline_task_id == task.id).order_by(SelectionPipelineKeyword.source_index)).all())
            update_pipeline_stage(db, task, stage="supplier_search", progress=10, message=f"正在按 {keyword_limit} 个关键词查询 1688，每个关键词 {supplier_page_size} 条", counters={"keywords": keyword_limit})
            for index, keyword_row in enumerate(keyword_rows, start=1):
                try:
                    result = search_1688_products(db, keyword_row.keyword, page=1, page_size=supplier_page_size)
                    for rank, item in enumerate(result.get("items") or [], start=1):
                        candidate = Selection1688Candidate(
                            pipeline_task_id=task.id,
                            keyword_id=keyword_row.id,
                            user_id=task.user_id,
                            keyword_rank=rank,
                            external_product_id=str(item.get("supplier_product_id") or ""),
                            title=str(item.get("title") or keyword_row.keyword)[:512],
                            image_url=str(item.get("image_url") or ""),
                            price=float(item.get("price") or 0),
                            sales_count=int(item.get("sales_count") or 0),
                            shop_name=str(item.get("shop_name") or "")[:255],
                            source_url=str(item.get("source_url") or ""),
                            raw_data=json.dumps(item.get("raw_data") or item, ensure_ascii=False),
                        )
                        db.add(candidate)
                    keyword_row.supplier_count = len(result.get("items") or [])
                    keyword_row.status = "supplier_collected"
                except Supplier1688Error as exc:
                    keyword_row.status = "supplier_failed"
                    keyword_row.raw_payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
                task.supplier_candidate_count = len(list(db.scalars(select(Selection1688Candidate).where(Selection1688Candidate.pipeline_task_id == task.id)).all()))
                db.commit()
                update_pipeline_stage(db, task, stage="supplier_search", progress=10 + int(index * 35 / max(len(keyword_rows), 1)), message=f"已完成 {index}/{len(keyword_rows)} 个 1688 关键词")

            all_candidates = list(db.scalars(select(Selection1688Candidate).where(Selection1688Candidate.pipeline_task_id == task.id)).all())
            by_keyword: dict[int, list[Selection1688Candidate]] = {}
            for candidate in all_candidates:
                by_keyword.setdefault(candidate.keyword_id, []).append(candidate)
            seeds: list[Selection1688Candidate] = []
            for keyword_id, candidates in by_keyword.items():
                candidates.sort(key=lambda item: (float(item.price or 0), item.id))
                for candidate in candidates:
                    candidate.status = "not_price_seed"
                image_candidates = [item for item in candidates if item.image_url]
                middle_index = max(0, (len(image_candidates) - 1) // 2)
                selected_seeds = image_candidates[:1]
                if len(image_candidates) > 1:
                    selected_seeds.append(image_candidates[middle_index])
                for seed_rank, candidate in enumerate(selected_seeds[:seed_per_keyword], start=1):
                    candidate.is_price_seed = 1
                    candidate.seed_rank = seed_rank
                    candidate.status = "price_seed"
                    seeds.append(candidate)
            db.commit()
            task.supplier_candidate_count = len(all_candidates)
            update_pipeline_stage(db, task, stage="price_seed_selection", progress=50, message=f"已从 1688 商品中选出 {len(seeds)} 个最低价图片种子", counters={"keywords": keyword_limit, "supplier_candidates": len(all_candidates), "image_search_entries": len(seeds)})

            for seed in seeds:
                entry = SelectionImageSearchEntry(
                    pipeline_task_id=task.id,
                    keyword_id=seed.keyword_id,
                    seed_candidate_id=seed.id,
                    user_id=task.user_id,
                    image_url=seed.image_url,
                    source_price=float(seed.price or 0),
                    status="pending",
                )
                db.add(entry)
                db.flush()
                try:
                    result = search_by_image(db, seed.image_url)
                    ids = result.get("product_ids") or []
                    entry.returned_id_count = len(ids)
                    entry.raw_response = json.dumps(result.get("raw_data") or {}, ensure_ascii=False)
                    entry.status = "success"
                    for product_id in ids:
                        db.add(SelectionDidadogProduct(
                            pipeline_task_id=task.id,
                            keyword_id=seed.keyword_id,
                            image_search_entry_id=entry.id,
                            user_id=task.user_id,
                            didadog_product_id=str(product_id),
                            detail_status="pending",
                        ))
                except EchoTikError as exc:
                    entry.status = "failed"
                    entry.raw_response = json.dumps({"error": str(exc)}, ensure_ascii=False)
                db.commit()
            didadog_count = len(list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task.id)).all()))
            task.image_search_entry_count = len(seeds)
            task.didadog_id_count = didadog_count
            update_pipeline_stage(db, task, stage="image_search", progress=70, message=f"以图搜款已完成，获得 {didadog_count} 个商品 ID")

            products = list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task.id, SelectionDidadogProduct.detail_status == "pending")).all())
            for start in range(0, len(products), 10):
                batch = products[start:start + 10]
                try:
                    details = get_product_details(db, [item.didadog_product_id for item in batch]).get("items") or []
                    details_by_id = {str(item.get("product_id") or item.get("productId") or item.get("id")): item for item in details if isinstance(item, dict)}
                    for product in batch:
                        raw = details_by_id.get(product.didadog_product_id, {})
                        product.title = str(raw.get("title") or raw.get("name") or raw.get("product_name") or "")[:512]
                        cover_value = raw.get("image_url") or raw.get("imageUrl") or raw.get("cover") or raw.get("cover_url") or ""
                        if isinstance(cover_value, str) and cover_value.startswith("["):
                            try:
                                cover_items = json.loads(cover_value)
                                cover_value = (cover_items[0] or {}).get("url") if isinstance(cover_items, list) and cover_items else ""
                            except (TypeError, ValueError, IndexError):
                                cover_value = ""
                        product.image_url = str(cover_value or "")
                        product.detail_url = str(raw.get("detail_url") or raw.get("url") or raw.get("share_url") or "")
                        product.price = float(raw.get("price") or raw.get("min_price") or raw.get("spu_avg_price") or 0)
                        product.sales_count = int(raw.get("sales_count") or raw.get("sales") or raw.get("sold_count") or raw.get("total_sale_cnt") or 0)
                        product.category = str(raw.get("category") or raw.get("category_name") or "")[:255]
                        product.detail_status = "success"
                        product.raw_data = json.dumps(raw, ensure_ascii=False)
                except EchoTikError as exc:
                    for product in batch:
                        product.detail_status = "failed"
                        product.raw_data = json.dumps({"error": str(exc)}, ensure_ascii=False)
                db.commit()
            task.didadog_detail_count = len([item for item in products if item.detail_status == "success"])
            detailed_products = [item for item in products if item.detail_status == "success"]
            update_pipeline_stage(db, task, stage="blue_ocean_filter", progress=78, message="正在按大模型商品分组，筛出 100 个低销量蓝海候选")
            grouped: dict[int, list[SelectionDidadogProduct]] = {}
            for product in detailed_products:
                grouped.setdefault(product.keyword_id, []).append(product)
            blue_ocean_pool: list[SelectionDidadogProduct] = []
            for group in grouped.values():
                group.sort(key=lambda item: (int(item.sales_count or 0), item.id))
                for product in group[2:]:
                    product.selection_status = "blue_ocean_eliminated"
                    _set_product_reason(product, "同大模型商品分组中销量较高，作为红海商品淘汰")
                for product in group[:2]:
                    product.selection_status = "blue_ocean_pool"
                    blue_ocean_pool.append(product)
            blue_ocean_pool.sort(key=lambda item: (-int(item.sales_count or 0), item.id))
            for product in blue_ocean_pool[:max(0, len(blue_ocean_pool) - 30)]:
                product.selection_status = "blue_ocean_eliminated"
                _set_product_reason(product, "销量排名靠前，淘汰以规避成熟红海商品")
            candidates = [item for item in blue_ocean_pool if item.selection_status == "blue_ocean_pool"]
            for product in candidates:
                product.selection_status = "candidate"
            task.candidate_count = len(candidates)
            # Blue-ocean ranking is performed per 1688 image seed: sum all
            # EchoTik sales returned for that seed, then keep the 30 lowest
            # sales seeds and send their products to compliance review.
            seed_groups: dict[int, list[SelectionDidadogProduct]] = {}
            for product in detailed_products:
                seed_groups.setdefault(product.image_search_entry_id, []).append(product)
            ranked_seed_groups = sorted(
                ((entry_id, group, sum(int(item.sales_count or 0) for item in group)) for entry_id, group in seed_groups.items()),
                key=lambda item: (item[2], item[0]),
            )
            keep_group_count = min(30, len(ranked_seed_groups))
            kept_seed_ids = {entry_id for entry_id, _, _ in ranked_seed_groups[:keep_group_count]}
            for entry_id, group, total_sales in ranked_seed_groups:
                for product in group:
                    if entry_id in kept_seed_ids:
                        product.selection_status = "candidate"
                    else:
                        product.selection_status = "blue_ocean_eliminated"
                        _set_product_reason(product, f"对应1688商品的 EchoTik 商品销量合计为 {total_sales}，蓝海筛选淘汰")
            candidates = [product for entry_id, group, _ in ranked_seed_groups if entry_id in kept_seed_ids for product in group]
            task.candidate_count = keep_group_count
            db.commit()
            update_pipeline_stage(db, task, stage="compliance_filter", progress=85, message=f"正在审核 {len(candidates)} 个候选商品的日本法规和禁运风险")
            _run_compliance_filter(db, candidates)
            db.commit()
            passed = [item for item in candidates if item.compliance_status == "passed"]
            update_pipeline_stage(db, task, stage="restriction_check", progress=91, message="正在查询限售库并标记需要报白的商品")
            _run_restriction_check(db, passed)
            db.commit()
            update_pipeline_stage(db, task, stage="final_selection", progress=96, message="正在从合规商品中精选最终 10 款")
            eligible = [item for item in passed if item.restriction_status != "restricted"]
            eligible.sort(key=lambda item: (int(item.sales_count or 0), item.id))
            for product in eligible[10:]:
                product.selection_status = "candidate"
            for product in eligible[:10]:
                product.selection_status = "final"
            task.final_count = len(eligible[:10])
            db.commit()
            update_pipeline_stage(db, task, stage="final_selection", progress=98, message="最终商品已确定，正在请求 general 大模型生成完整市场报告")
            report_candidates = [item for item in candidates if item.selection_status == "candidate"]
            report_finals = [item for item in candidates if item.selection_status == "final"]
            report_analysis = _generate_report_analysis(db, task, report_candidates, report_finals)
            task.status = "success"
            task.current_stage = "final_selection"
            task.stage_progress = 100
            task.finished_at = datetime.utcnow()
            task.result_snapshot = json.dumps({"targets": _pipeline_targets(keyword_limit, supplier_page_size, seed_per_keyword), "test_mode": test_mode, "message": "已完成选品流程和市场报告分析", "report_analysis": report_analysis}, ensure_ascii=False)
            db.commit()
        except Exception as exc:
            _write_error(db, task, str(exc))
