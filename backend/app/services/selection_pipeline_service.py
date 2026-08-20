from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timedelta
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
    UserSearchRecommendation,
)
from app.services.ai_model_service import MODEL_TYPE_GENERAL, ModelCallError, chat_completion, extract_json_object
from app.services.echotik_service import EchoTikError, get_product_details, search_by_image
from app.services.restriction_weight_service import restriction_weights_for_product, restriction_weights_prompt
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
    keyword_limit = max(5, get_setting_int(db, "selection_pipeline_test_keywords")) if test_mode else 35
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


def _fallback_positioning(products: list[dict[str, Any]]) -> dict[str, str]:
    """基于商品标题关键词做保守但具体的产品定位兜底。"""
    titles = " ".join(p.get("title") or "" for p in products).lower()
    category = " ".join(p.get("category") or "" for p in products).lower()
    combined = titles + " " + category

    if any(k in combined for k in ("化妆", "护肤", "美妆", "口红", "眼影", "面膜", "精华")):
        return {
            "positioning": "面向日本年轻女性的日常美妆护肤小物，主打性价比与便携体验。",
            "selling_point": "成分温和、包装精致、适合通勤或旅行随身携带。",
            "style": "清新自然、韩系/日系少女感，强调无负担与快速上妆。",
        }
    if any(k in combined for k in ("厨房", "收纳", "家居", "清洁", "餐具", "置物", "沥水")):
        return {
            "positioning": "面向日本小户型家庭的实用型家居收纳与厨房 helper，解决空间局促痛点。",
            "selling_point": "结构简单、易清洗、节省台面空间，提升日常家务效率。",
            "style": "极简素色、MUJI 风，强调功能优先与耐用。",
        }
    if any(k in combined for k in ("宠物", "猫", "狗", "犬", "喵", "汪")):
        return {
            "positioning": "面向日本宠物主人的日常消耗与陪伴用品，主打安全与趣味。",
            "selling_point": "材质安全、互动性强，满足宠物玩耍与主人拍摄短视频需求。",
            "style": "温馨可爱、ins 风，色彩柔和适合社交平台传播。",
        }
    if any(k in combined for k in ("户外", "运动", "健身", "瑜伽", "跑步", "露营")):
        return {
            "positioning": "面向日本都市运动与户外爱好者，强调轻便、耐用与场景适配。",
            "selling_point": "便携易收纳、功能明确，适合周末轻户外或居家健身。",
            "style": "机能风、运动休闲，强调活力与实用。",
        }
    if any(k in combined for k in ("数码", "电子", "配件", "充电", "线", "耳机", "手机壳")):
        return {
            "positioning": "面向日本数码用户的实用配件，主打性价比与兼容性。",
            "selling_point": "解决接口不匹配、收纳凌乱等日常小痛点，使用高频。",
            "style": "科技极简、黑白灰为主，强调细节做工。",
        }
    if any(k in combined for k in ("儿童", "宝宝", "婴儿", "母婴", "玩具", "绘本")):
        return {
            "positioning": "面向日本新手父母的母婴与儿童用品，主打安全与陪伴。",
            "selling_point": "材质安全、设计圆润、便于家长清洁与收纳。",
            "style": "柔和马卡龙色、卡通元素，传递安心与童趣。",
        }
    if any(k in combined for k in ("服装", "服饰", "穿搭", "T恤", "裙子", "外套")):
        return {
            "positioning": "面向日本年轻消费者的潮流服饰单品，强调季节感与搭配性。",
            "selling_point": "版型适配亚洲身材、面料舒适，适合日常通勤或周末出游。",
            "style": "简约街头或日系通勤风，注重细节与百搭。",
        }
    return {
        "positioning": "面向日本 TikTok 用户的日常消费小物，主打实用与性价比。",
        "selling_point": "功能明确、价格亲民，适合短视频种草与冲动下单。",
        "style": "简洁实用，包装与展示突出使用场景。",
    }


def _fallback_audience(products: list[dict[str, Any]]) -> dict[str, str]:
    """基于商品标题关键词做保守但具体的目标受众兜底。"""
    titles = " ".join(p.get("title") or "" for p in products).lower()
    category = " ".join(p.get("category") or "" for p in products).lower()
    combined = titles + " " + category

    if any(k in combined for k in ("化妆", "护肤", "美妆", "口红", "眼影", "面膜")):
        return {
            "persona": "18-35 岁注重颜值与护肤的日本年轻女性（女性为主，学生与职场新人占比高），活跃于 TikTok 与 Instagram。",
            "age_gender": "18-35 岁女性为主，学生与职场新人占比高。",
            "pain_point": "预算有限但想尝试新品，担心成分刺激或妆效不持久。",
            "scene": "晨起通勤、约会前补妆、旅行途中快速打理。",
        }
    if any(k in combined for k in ("厨房", "收纳", "家居", "清洁", "餐具", "置物")):
        return {
            "persona": "25-45 岁日本家庭主妇与独居租房者（女性为主，独居青年与双职工家庭并重），重视空间利用与清洁效率。",
            "age_gender": "25-45 岁女性为主，独居青年与双职工家庭并重。",
            "pain_point": "居住面积小、物品多，希望低价解决收纳与清洁难题。",
            "scene": "日常厨房整理、浴室清洁、换季收纳。",
        }
    if any(k in combined for k in ("宠物", "猫", "狗", "犬")):
        return {
            "persona": "25-45 岁日本宠物主（男女均有，女性略多），把宠物视为家庭成员，愿意为爱宠消费。",
            "age_gender": "25-45 岁男女均有，女性略多。",
            "pain_point": "市面宠物用品价格高、款式单一，想找有趣又安全的替代品。",
            "scene": "居家陪伴、外出遛宠、宠物生日或节日社交分享。",
        }
    if any(k in combined for k in ("户外", "运动", "健身", "瑜伽", "跑步", "露营")):
        return {
            "persona": "20-40 岁日本运动与户外爱好者（男女均衡，职场白领与学生群体为主），追求健康生活方式。",
            "age_gender": "20-40 岁男女均衡，职场白领与学生群体为主。",
            "pain_point": "专业装备贵、携带不便，希望找到轻便且高性价比的入门装备。",
            "scene": "周末徒步、居家健身、公园跑步、轻露营。",
        }
    if any(k in combined for k in ("数码", "电子", "配件", "充电", "线", "耳机")):
        return {
            "persona": "18-40 岁日本数码消费者（男性为主，女性用户随手机周边增长），男性略多，关注兼容性与耐用度。",
            "age_gender": "18-40 岁男性为主，女性用户随手机周边增长。",
            "pain_point": "原装配件贵、线材易坏、接口不统一。",
            "scene": "通勤途中、办公桌前、旅行出差、游戏娱乐。",
        }
    if any(k in combined for k in ("儿童", "宝宝", "婴儿", "母婴", "玩具")):
        return {
            "persona": "25-40 岁日本新手父母（父母为主，母亲决策占比高），重视安全、耐摔与易清洁。",
            "age_gender": "25-40 岁父母为主，母亲决策占比高。",
            "pain_point": "母婴店价格贵、款式同质化，希望找到安全且有趣的平价替代品。",
            "scene": "居家陪伴、外出哄娃、亲友送礼、节日拍照。",
        }
    if any(k in combined for k in ("服装", "服饰", "穿搭", "T恤", "裙子")):
        return {
            "persona": "18-35 岁日本年轻消费者（女性为主，男性潮牌用户为辅），关注季节穿搭与社交媒体潮流。",
            "age_gender": "18-35 岁女性为主，男性潮牌用户为辅。",
            "pain_point": "快时尚质量不稳定，想找价格合适又有设计感的单品。",
            "scene": "日常通勤、周末出游、约会、社交媒体晒图。",
        }
    return {
        "persona": "18-45 岁日本普通消费者（男女不限，年轻女性与家庭主妇为主力），价格敏感且容易被短视频种草。",
        "age_gender": "18-45 岁男女不限，年轻女性与家庭主妇为主力。",
        "pain_point": "日常小物件购买渠道有限或价格偏高，希望找到实用平价替代品。",
        "scene": "居家生活、通勤途中、周末休闲、节日送礼。",
    }


EVASIVE_HINTS = (
    "需进一步验证", "暂未获取", "暂未", "缺乏公开", "缺乏权威", "缺乏可", "待补充",
    "待确认", "数据缺失", "暂无精准", "未获取到", "时序增长数据", "有待核验",
    "无法获取", "缺少权威", "暂无权威", "未获取到明确", "缺乏明确", "尚不明朗",
    "暂无可靠", "未能获取", "暂无公开的", "暂无对外", "暂无第三方",
)


def _is_evasive(text: str) -> bool:
    """检测是否仍是借数据缺失推脱的占位话术。"""
    t = text.lower()
    return any(hint in t for hint in EVASIVE_HINTS)


def _fallback_market_intro(products: list[dict[str, Any]]) -> dict[str, str]:
    """基于商品标题关键词给出具体但保守的市场简介兜底，禁止占位话术。"""
    titles = " ".join(p.get("title") or "" for p in products).lower()
    category = " ".join(p.get("category") or "" for p in products).lower()
    combined = titles + " " + category

    if any(k in combined for k in ("化妆", "护肤", "美妆", "口红", "眼影", "面膜", "精华")):
        return {
            "market_scale": "日本美妆个护市场规模常年位居全球前列，年零售额超数万亿日元，TikTok 渠道仍处高速增长期，年轻女性为核心购买力。",
            "demand_trend": "妆教与种草内容在 TikTok 持续走热，平价好物与成分党需求快速放量，复购意愿强。",
            "competition_landscape": "国际大牌与本土药妆品牌占据主流，但平价细分与差异化卖点仍有大量空白可被内容种草切入。",
        }
    if any(k in combined for k in ("厨房", "收纳", "家居", "清洁", "餐具", "置物", "沥水")):
        return {
            "market_scale": "日本住宅面积偏小，收纳清洁为刚需高频类目，市场规模稳定且体量庞大，线上渗透持续提升。",
            "demand_trend": "MUJI 风、极简功能性产品接受度高，短视频展示使用场景的转化效果明显。",
            "competition_landscape": "本土品牌成熟，但高性价比、强场景化的供应链商品仍有差异化空间。",
        }
    if any(k in combined for k in ("宠物", "猫", "狗", "犬")):
        return {
            "market_scale": "日本宠物经济成熟且持续增长，宠物主将宠物视为家人，用品、零食、互动玩具复购率高。",
            "demand_trend": "宠物陪伴与社交分享内容在 TikTok 受欢迎，有趣又安全的替代品需求旺盛。",
            "competition_landscape": "本土宠物品牌较多，但趣味化、平价化供给仍不充分，出海空间明显。",
        }
    if any(k in combined for k in ("户外", "运动", "健身", "瑜伽", "跑步", "露营")):
        return {
            "market_scale": "疫情后健康生活与轻户外需求上升，便携装备市场稳步扩大，入门级消费占比提升。",
            "demand_trend": "周末徒步、居家健身内容在社媒增长，轻便高性价比入门装备种草转化明显。",
            "competition_landscape": "专业品牌价格偏高，平价入门替代品尚不充分，内容驱动转化效率高。",
        }
    if any(k in combined for k in ("数码", "电子", "配件", "充电", "线", "耳机", "手机壳")):
        return {
            "market_scale": "日本 3C 配件市场庞大且稳定，手机周边与充电类目高频复购，女性用户随手机壳增长。",
            "demand_trend": "兼容性、耐用性与颜值并重的实用配件需求稳定，短视频开箱测评转化好。",
            "competition_landscape": "原装与本土品牌占主流，但高性价比第三方配件仍有充足空间。",
        }
    if any(k in combined for k in ("儿童", "宝宝", "婴儿", "母婴", "玩具", "绘本")):
        return {
            "market_scale": "日本少子化下母婴消费更重品质安全，客单高、复购稳，新手父母愿为安全有趣产品付费。",
            "demand_trend": "安全、耐摔、易清洁的育儿用品需求刚性，社媒母婴博主种草影响力强。",
            "competition_landscape": "本土母婴品牌强势，但平价安全替代品仍有切入机会。",
        }
    if any(k in combined for k in ("服装", "服饰", "穿搭", "T恤", "裙子", "外套")):
        return {
            "market_scale": "日本时尚消费成熟，季节穿搭与社媒潮流驱动，平价有设计感单品市场空间充足。",
            "demand_trend": "日常通勤与周末出游穿搭内容热度高，百搭基础款与潮牌平替需求稳定。",
            "competition_landscape": "快时尚同质化严重，有设计感且价格合适的差异化单品仍有空白。",
        }
    return {
        "market_scale": "日本 TikTok 电商处于高速增长期，内容种草转化效率高于传统货架，日用消费小物市场广阔。",
        "demand_trend": "短视频种草驱动冲动消费，平价实用小物的需求持续放量。",
        "competition_landscape": "头部品类竞争激烈，但大量细分蓝海仍待内容切入。",
    }


def _ensure_concrete_fields(parsed: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """确保产品定位与目标受众字段有具体内容，禁止占位符。"""
    placeholders = ("需进一步验证", "待定", "暂无", "unknown", "n/a", "待确认", "")
    fallback_pos = _fallback_positioning(products)
    fallback_aud = _fallback_audience(products)

    pp = parsed.get("product_positioning") if isinstance(parsed.get("product_positioning"), dict) else {}
    pp = {
        "positioning": str(pp.get("positioning") or "").strip(),
        "selling_point": str(pp.get("selling_point") or "").strip(),
        "style": str(pp.get("style") or "").strip(),
    }
    for key, val in fallback_pos.items():
        if pp.get(key, "").lower() in placeholders or _is_evasive(pp.get(key, "")):
            pp[key] = val

    ta = parsed.get("target_audience") if isinstance(parsed.get("target_audience"), dict) else {}
    ta = {
        "persona": str(ta.get("persona") or "").strip(),
        "age_gender": str(ta.get("age_gender") or "").strip(),
        "pain_point": str(ta.get("pain_point") or "").strip(),
        "scene": str(ta.get("scene") or "").strip(),
    }
    for key, val in fallback_aud.items():
        if ta.get(key, "").lower() in placeholders or _is_evasive(ta.get(key, "")):
            ta[key] = val
    # 年龄性别并入人群画像，避免单列冗余
    if ta["age_gender"] and ta["age_gender"] not in ta["persona"]:
        ta["persona"] = f"{ta['persona']}（{ta['age_gender']}）" if ta["persona"] else ta["age_gender"]
    ta["age_gender"] = ""

    parsed["product_positioning"] = pp
    parsed["target_audience"] = ta

    mi = parsed.get("market_intro") if isinstance(parsed.get("market_intro"), dict) else {}
    mi = {
        "market_scale": str(mi.get("market_scale") or "").strip(),
        "demand_trend": str(mi.get("demand_trend") or "").strip(),
        "competition_landscape": str(mi.get("competition_landscape") or "").strip(),
    }
    fallback_mkt = _fallback_market_intro(products)
    for key, val in fallback_mkt.items():
        if mi.get(key, "").lower() in placeholders or _is_evasive(mi.get(key, "")):
            mi[key] = val
    parsed["market_intro"] = mi
    return parsed


def _generate_report_analysis(db: Session, task: SelectionPipelineTask, candidates: list[SelectionDidadogProduct], finals: list[SelectionDidadogProduct], portfolio_hint: str | None = None) -> dict[str, Any]:
    products = [
        {
            "title": item.title or item.didadog_product_id,
            "category": item.category,
            "price": item.price,
            "sales_count": item.sales_count,
            "selection_status": item.selection_status,
            "restriction_status": item.restriction_status,
        }
        for item in [*candidates, *finals]
    ]
    if not products:
        products = [{"title": task.input_message or "用户需求", "category": "", "price": None, "sales_count": None}]
    prompt = (
        "你是日本 TikTok 跨境电商资深选品顾问。请根据本次已经完成筛选的商品生成中文市场分析报告。\n"
        "只能基于输入商品和任务需求做谨慎判断，不要虚构具体市场规模、销量、法规结论或外部数据。\n"
        "但商品标题、类目、价格、销量已经足以做出合理推断，因此你必须给出具体、可落地的分析结论，"
        "严禁返回‘需进一步验证’‘待定’‘暂无’‘未知’等占位性文字。\n"
        "必须严格返回 JSON，不要 Markdown，字段必须包含：\n"
        "market_intro（对象，必须包含 market_scale 市场规模、demand_trend 需求趋势、competition_landscape 竞争格局三项，每项150字以内）；"
        "三项都必须由你作为资深顾问直接给出专业、具体的方向性判断，禁止出现任何以数据缺失为借口的表述，"
        "包括但不限于‘暂无精准公开量化数据’‘暂未获取到搜索量/播放量’‘待补充平台流量监测’‘缺乏权威数据’‘需进一步验证’‘时序增长数据’等。\n"
        "你应基于日本 TikTok/社媒生态、该类目的消费节奏、内容种草形态、季节与节日驱动、KOL 带动等行业常识进行严谨推断："
        "market_scale 写该类目在日本市场的普遍体量、渠道增速与消费特征；demand_trend 写增长动能、内容风向与购买驱动；"
        "competition_landscape 写品牌格局与差异化切入机会。\n"
        "opportunity_tracks（数组，最多3项，每项包含 track_name、opportunity、reason）、\n"
        "product_positioning（对象，产品定位画像，包含 positioning 定位描述、selling_point 核心卖点、style 风格调性，每项120字以内）、\n"
        "target_audience（对象，目标受众分析，包含 persona 人群画像、age_gender 年龄性别、pain_point 痛点需求、scene 使用场景，每项120字以内）；"
        "注意：persona 必须直接包含年龄与性别描述，不要依赖 age_gender 单独字段，age_gender 仅作简短复述。\n"
        "restriction_flags（数组，平台限售标注；依据商品 restriction_status=restricted 命中日本限售的类目及说明，无则空数组）、\n"
        "candidate_strategy（150字以内）、final_strategy（150字以内）、risk_advice（数组最多5条）、conclusion（100字以内）。\n"
        "蓝海原则：销量高代表成熟竞争，不等于优先推荐；重点分析低销量但有需求验证、供应链可做、差异化空间足的商品。\n"
        f"用户需求：{task.input_message}\n商品数据：{json.dumps(products, ensure_ascii=False)}"
    )
    if portfolio_hint:
        prompt += (
            f"\n本次最终 10 款精选的组合分布为：{portfolio_hint}。"
            "请在 final_strategy 与 conclusion 中自然体现这一『爆款+常规+新品+奇特+亮点』多元组合思路，"
            "说明其兼顾已验证需求与内容出圈潜力，但严禁编造具体销量数字。"
        )
    try:
        answer = chat_completion(
            db,
            [{"role": "system", "content": "你负责生成严谨、可落地的日本市场选品报告。必须基于已有商品数据给出具体结论，禁止用占位符敷衍。"}, {"role": "user", "content": prompt}],
            model_type=MODEL_TYPE_GENERAL,
            temperature=0.25,
            max_tokens=3500,
        )
        parsed = extract_json_object(answer)
        if not isinstance(parsed, dict):
            parsed = {"market_intro": {"market_scale": str(answer)}}
        parsed = _ensure_concrete_fields(parsed, products)
        return parsed
    except (ModelCallError, ValueError, TypeError) as exc:
        pos = _fallback_positioning(products)
        aud = _fallback_audience(products)
        return {
            "market_intro": {
                "market_scale": "本次筛选商品尚未接入外部市场规模数据，可从商品热度与销量趋势间接推断需求。",
                "demand_trend": "基于输入关键词与候选品销售数据，判断为日常稳定需求型或季节性波动型。",
                "competition_landscape": "本任务按低销量蓝海逻辑筛选，避开头部爆款，聚焦差异化长尾。",
            },
            "opportunity_tracks": [],
            "product_positioning": pos,
            "target_audience": aud,
            "restriction_flags": [],
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


def _jp_trend_calendar(now: datetime) -> str:
    """根据日本当地月份返回当前值得关注的趋势节点背景，注入关键词生成。"""
    month = now.month
    calendar = [
        ((1, 2), "年賀状/お歳暮余韵、寒冬保暖、節分(2月)恵方巻与除魔周边"),
        ((2, 3, 4), "新学期/入学/引越し新生活、春物衣装、花粉症对策"),
        ((3, 4, 5), "母の日(5月)、こどもの日、黄金周出游、梅雨(5-7月)除湿防霉"),
        ((5, 6, 7), "お中元(7月)、夏支度、梅雨除湿防霉、暑さ対策预热"),
        ((6, 7, 8), "夏休み/暑さ対策/UV日焼け、お中元(7月)、防災(9/1防災の日)备蓄"),
        ((8, 9, 10), "防災月間、運動会/スポーツの日、ハロウィン(10/31)装扮与装饰"),
        ((10, 11, 12), "クリスマス/年末ギフト、寒さ対策、紅葉狩り出行"),
        ((11, 12, 1), "クリスマス/お歳暮/年賀状礼品季、寒冬保暖"),
    ]
    text = ""
    for months, desc in calendar:
        if month in months:
            text = desc
            break
    evergreen = (
        "常年高关注：ペット(宠物)、韓国風(韩系)、キャンプ/アウトドア(露营)、"
        "収納(收纳)、美容/痩身(美容瘦身)、在宅ワーク(居家)、節約/防犯(省钱安防)、"
        "子供/ベビー(母婴)、ギフト(礼品)。"
    )
    return f"{text}；{evergreen}" if text else evergreen


# (term, active_months, weight)；active_months 为空表示常年有效
_TREND_TERMS: list[tuple[str, tuple[int, ...], int]] = [
    ("ハロウィン", (9, 10), 3), ("halloween", (9, 10), 3),
    ("クリスマス", (11, 12), 3), ("christmas", (11, 12), 3),
    ("お中元", (5, 6, 7), 3), ("中元", (5, 6, 7), 3),
    ("梅雨", (5, 6, 7), 2), ("除湿", (5, 6, 7, 8), 2), ("防霉", (5, 6, 7), 2),
    ("夏休", (7, 8), 2), ("日焼け", (6, 7, 8), 2), ("uv", (6, 7, 8), 2),
    ("防災", (8, 9), 3), ("備蓄", (8, 9), 2),
    ("新学期", (2, 3, 4), 2), ("入学", (2, 3, 4), 2), ("引越", (2, 3, 4), 2),
    ("節分", (1, 2), 2), ("恵方", (1, 2), 2),
    ("運動会", (9, 10), 2), ("スポーツの日", (9, 10), 2),
    ("年賀", (12, 1), 2), ("お歳暮", (11, 12), 2),
    ("ペット", (), 1), ("猫", (), 1), ("犬", (), 1),
    ("韓国", (), 1), ("キャンプ", (), 1), ("アウトドア", (), 1),
    ("収納", (), 1), ("美容", (), 1), ("痩", (), 1),
    ("在宅", (), 1), ("節約", (), 1), ("防犯", (), 1),
    ("ベビー", (), 1), ("子供", (), 1), ("ギフト", (), 1),
]


def _trend_score(title: str, category: str, now: datetime) -> int:
    """趋势分：标题/类目命中的季节性或常年趋势词加权求和。"""
    text = f"{(title or '')} {(category or '')}".lower()
    month = now.month
    score = 0
    for term, months, weight in _TREND_TERMS:
        if term.lower() in text and (not months or month in months):
            score += weight
    return score


def _write_selection_meta(
    product: SelectionDidadogProduct,
    novelty: int | None = None,
    content: int | None = None,
    reason: str | None = None,
    tier: str | None = None,
) -> None:
    """把新意打分/亮点理由/分层写入商品的 selection_meta（JSON 列，可增量更新）。"""
    try:
        meta = json.loads(product.selection_meta or "{}")
    except (TypeError, ValueError):
        meta = {}
    if novelty is not None:
        meta["novelty"] = novelty
    if content is not None:
        meta["content"] = content
    if reason is not None:
        meta["reason"] = reason
    if tier is not None:
        meta["tier"] = tier
    product.selection_meta = json.dumps(meta, ensure_ascii=False)


def _score_novelty_content(db: Session, products: list[SelectionDidadogProduct]) -> dict[int, dict[str, Any]]:
    """批量给候选商品打新意分(novelty)与内容友好度分(content)，并给一句亮点理由。"""
    result: dict[int, dict[str, Any]] = {
        p.id: {"novelty": 50, "content": 50, "reason": ""} for p in products
    }
    if not products:
        return result
    items = [
        {
            "idx": idx,
            "title": (p.title or "")[:80],
            "category": (p.category or "")[:40],
            "price": p.price or 0,
            "sales": p.sales_count or 0,
        }
        for idx, p in enumerate(products)
    ]
    prompt = (
        "你是日本 TikTok 跨境选品的新意评审。下面是一批已通过合规的候选商品。\n"
        "请对每件商品评估两个 0-100 分数，并写一句不超过 25 字的中文亮点理由：\n"
        "novelty（差异化/新意）：是否是非常规组合、新场景、新形态，避开大同小异的爆款同款；越独特越高。\n"
        "content（内容友好度）：是否适合 TikTok 短视频出圈——视觉冲击、开箱惊喜、before-after 反差、有梗、易演示。\n"
        "请严格返回 JSON 数组，每项格式 {idx:原序号, novelty:整数, content:整数, reason:一句话}。不要 Markdown，不要解释。"
    )
    try:
        answer = chat_completion(
            db,
            [
                {"role": "system", "content": "你是选品新意评审，只输出 JSON。"},
                {"role": "user", "content": prompt + "\n商品列表：\n" + json.dumps(items, ensure_ascii=False)},
            ],
            model_type=MODEL_TYPE_GENERAL,
            max_tokens=4000,
            temperature=0.4,
        )
        parsed = extract_json_object(answer)
        if isinstance(parsed, dict):
            parsed = parsed.get("items") or parsed.get("keywords") or []
        if isinstance(parsed, list):
            for row in parsed:
                if not isinstance(row, dict):
                    continue
                idx = row.get("idx")
                if not isinstance(idx, int) or idx < 0 or idx >= len(products):
                    continue
                try:
                    nov = int(row.get("novelty") or 50)
                    con = int(row.get("content") or 50)
                except (TypeError, ValueError):
                    nov, con = 50, 50
                result[products[idx].id] = {
                    "novelty": max(0, min(100, nov)),
                    "content": max(0, min(100, con)),
                    "reason": str(row.get("reason") or "").strip()[:40],
                }
    except Exception:
        pass
    return result


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
        "请按照日本法规、禁运、禁售、平台限制、专利侵权、商标侵权、海关报关与检疫受限审核以下商品。"
        "判断维度：①禁运/禁售；②平台限售；③专利或商标侵权（含外观设计）；④海关报关受限或需检疫检验（如食品、药品、动植物、医疗器械）。只输出 JSON。"
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


def _auto_add_selected_products_to_library(
    db: Session,
    task: SelectionPipelineTask,
    report_analysis: dict[str, Any],
) -> None:
    """智能选品任务成功后，自动把候选品和精选品写入用户选品库（带 task_id 去重）。"""
    user_id = int(task.user_id or 0)
    if not user_id:
        return

    selected_products = list(db.scalars(
        select(SelectionDidadogProduct)
        .where(
            SelectionDidadogProduct.pipeline_task_id == task.id,
            SelectionDidadogProduct.selection_status.in_(["candidate", "final"]),
        )
    ).all())
    if not selected_products:
        return

    entry_ids = {p.image_search_entry_id for p in selected_products if p.image_search_entry_id}
    entries = list(db.scalars(
        select(SelectionImageSearchEntry)
        .where(SelectionImageSearchEntry.id.in_(entry_ids))
    ).all()) if entry_ids else []
    entry_map = {e.id: e for e in entries}
    candidate_ids = {e.seed_candidate_id for e in entries if e.seed_candidate_id}
    candidates = list(db.scalars(
        select(Selection1688Candidate)
        .where(Selection1688Candidate.id.in_(candidate_ids))
    ).all()) if candidate_ids else []
    candidate_map = {c.id: c for c in candidates}

    tier_labels = {
        "hot": "爆款",
        "regular": "常规",
        "new": "新品",
        "quirky": "奇特",
        "highlight": "亮点",
    }

    existing_keys: set[tuple[int, str]] = set()
    for p in selected_products:
        title = str(p.title or "").strip()
        if not title:
            continue
        if (task.id, title) in existing_keys:
            continue
        existing = db.scalar(
            select(UserSearchRecommendation).where(
                UserSearchRecommendation.user_id == user_id,
                UserSearchRecommendation.task_id == task.id,
                UserSearchRecommendation.title == title,
            )
        )
        if existing:
            existing_keys.add((task.id, title))
            continue

        entry = entry_map.get(p.image_search_entry_id)
        candidate = candidate_map.get(entry.seed_candidate_id) if entry else None
        meta: dict[str, Any]
        try:
            meta = json.loads(p.selection_meta or "{}")
        except (TypeError, ValueError):
            meta = {}
        tier = str(meta.get("tier") or "regular")
        reason = str(meta.get("reason") or "").strip()
        tier_label = tier_labels.get(tier, "精选")

        report_payload = {
            "tier": tier,
            "tier_label": tier_label,
            "selection_reason": reason,
            # 智能选品/衍生品的价格来自 1688 供应链，写入选品库时统一按中国货源展示。
            # EchoTik 查询仍使用日本站参数，但不能把平台查询地区当成商品货币地区。
            "_library_region": "CN",
            "_library_currency": "CNY",
            "_library_category": str(p.category or ""),
            "didadog_product_id": str(p.didadog_product_id or ""),
            "pipeline_report_summary": report_analysis.get("executive_summary") or "",
        }

        item = UserSearchRecommendation(
            user_id=user_id,
            task_id=task.id,
            search_query=str(task.input_message or "智能选品")[:255],
            source_type="ai_search",
            title=title,
            image_url=str(p.image_url or ""),
            price=float(p.price or 0),
            region="CN",
            currency="CNY",
            sales_count=int(p.sales_count or 0),
            reason_summary=f"来自 AI 智能选品：{tier_label}款。{reason}"[:500],
            analysis_report=json.dumps(report_payload, ensure_ascii=False),
            supplier_product_id=str(candidate.external_product_id or "") if candidate else "",
            supplier_title=str(candidate.title or "") if candidate else "",
            supplier_image_url=str(candidate.image_url or "") if candidate else "",
            supplier_price=float(candidate.price or 0) if candidate else None,
            supplier_sales_count=int(candidate.sales_count or 0) if candidate else 0,
            supplier_shop_name=str(candidate.shop_name or "") if candidate else "",
            supplier_source_url=str(candidate.source_url or "") if candidate else "",
            sort_order=0,
            created_at=datetime.utcnow(),
        )
        db.add(item)
        existing_keys.add((task.id, title))

    db.commit()


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
                weights, match_info = restriction_weights_for_product(
                    db,
                    title=source_product.title,
                    category=getattr(source_product, "category", ""),
                    region=getattr(source_product, "region", "JP"),
                )
                constant += restriction_weights_prompt(weights, match_info)
            trend_note = _jp_trend_calendar(datetime.utcnow() + timedelta(hours=9))
            prompt = (
                f"{constant}\n\n用户需求：{input_message}\n"
                f"当前月份日本站趋势背景：{trend_note}\n"
                f"请只输出 JSON 数组，生成 {keyword_limit} 个{('适合该原商品衍生的' if derivation_mode else '适合 TikTok 日本站蓝海选品的')}完整商品名称。\n"
                "要求：\n"
                "1. 必须是「具体场景/人群 + 功能 + 形态」的细分商品名，不要泛类目词"
                "（如避免只写'收纳盒''数据线'，要写成'租房党免打孔浴室置物架'这类具体款）。\n"
                "2. 主动结合上面的趋势背景，并制造反常规跨品类组合"
                "（如 宠物×美容、在宅×防災、收纳×展示型家居），制造差异与新意，避开大同小异的爆款同款。\n"
                "3. 全部使用简体中文，适合 1688 中文搜索；不要日文/英文；不要编号、不要解释、不要重复。"
            )
            answer = chat_completion(
                db,
                [{"role": "system", "content": "你是日本 TikTok 跨境选品关键词专家，只输出 JSON。"}, {"role": "user", "content": prompt}],
                model_type=MODEL_TYPE_GENERAL,
                max_tokens=6000,
                temperature=0.6,
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

            # EchoTik 全部失败时，使用本轮选出的 1688 图片种子继续完成筛选。
            # 这些记录沿用 SelectionDidadogProduct 结构，后面的蓝海、法规、限售和精选逻辑
            # 可以继续复用；selection_meta 用于让前端/报告知道这是 1688 降级数据。
            if not detailed_products:
                entry_rows = list(db.scalars(select(SelectionImageSearchEntry).where(SelectionImageSearchEntry.pipeline_task_id == task.id)).all())
                entry_by_seed = {item.seed_candidate_id: item for item in entry_rows}
                fallback_seeds = sorted(
                    [seed for seed in seeds if seed.image_url and entry_by_seed.get(seed.id)],
                    key=lambda item: (
                        0 if item.image_url else 1,
                        0 if float(item.price or 0) > 0 else 1,
                        int(item.sales_count or 0),
                        str(item.title or ""),
                        item.id,
                    ),
                )[:10]
                for seed in fallback_seeds:
                    entry = entry_by_seed[seed.id]
                    fallback_id = f"1688-fallback-{seed.external_product_id or seed.id}"
                    db.add(SelectionDidadogProduct(
                        pipeline_task_id=task.id,
                        keyword_id=seed.keyword_id,
                        image_search_entry_id=entry.id,
                        user_id=task.user_id,
                        didadog_product_id=fallback_id,
                        title=str(seed.title or "")[0:512],
                        image_url=str(seed.image_url or ""),
                        detail_url=str(seed.source_url or ""),
                        price=float(seed.price or 0),
                        currency=seed.currency or "CNY",
                        sales_count=int(seed.sales_count or 0),
                        category=str(getattr(seed, "category", "") or "")[0:255],
                        detail_status="success",
                        selection_status="candidate",
                        selection_meta=json.dumps({"fallback_source": "1688", "fallback_reason": "EchoTik 图片搜索失败"}, ensure_ascii=False),
                        raw_data=seed.raw_data or "{}",
                    ))
                db.commit()
                products = list(db.scalars(select(SelectionDidadogProduct).where(SelectionDidadogProduct.pipeline_task_id == task.id)).all())
                detailed_products = [item for item in products if item.detail_status == "success"]
                task.didadog_detail_count = 0
                update_pipeline_stage(db, task, stage="image_search", progress=72, message=f"EchoTik 暂无返回，已降级使用 {len(fallback_seeds)} 个 1688 商品继续筛选")

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
            update_pipeline_stage(db, task, stage="final_selection", progress=96, message="正在按五类组合（爆款/常规/新品/奇特/亮点）精选最终 10 款")
            eligible = [item for item in passed if item.restriction_status != "restricted"]
            now = datetime.utcnow() + timedelta(hours=9)
            scores = _score_novelty_content(db, eligible)
            for product in eligible:
                meta = scores.get(product.id, {"novelty": 50, "content": 50, "reason": ""})
                _write_selection_meta(
                    product,
                    novelty=meta["novelty"],
                    content=meta["content"],
                    reason=meta["reason"],
                )
            db.commit()

            # —— 销量相对归一化（0-1），用于区分爆款/常规/新品 ——
            sales_vals = [int(p.sales_count or 0) for p in eligible]
            s_min, s_max = (min(sales_vals), max(sales_vals)) if sales_vals else (0, 0)

            def _sales_norm(p: SelectionDidadogProduct) -> float:
                if s_max <= s_min:
                    return 0.5
                return (int(p.sales_count or 0) - s_min) / (s_max - s_min)

            # —— 五类分层：爆款 / 常规 / 新品 / 奇特 / 亮点 ——
            TIER_DEFS = {"hot": "爆款", "regular": "常规", "new": "新品", "quirky": "奇特", "highlight": "亮点"}
            TIER_REASON = {
                "hot": "已验证高销量爆款，需求确定易起量",
                "regular": "常规稳健款，低风险好上手",
                "new": "踩中近期日本趋势，处于上升期",
                "quirky": "形态/功能非常规，视觉吸睛有话题",
                "highlight": "",  # 亮点用 LLM 生成的差异化理由
            }
            TREND_THRESHOLD = 3

            def _classify(p: SelectionDidadogProduct) -> str:
                sc = scores.get(p.id, {"novelty": 50, "content": 50, "reason": ""})
                nov, con = sc["novelty"], sc["content"]
                tr = _trend_score(p.title, p.category, now)
                sn = _sales_norm(p)
                if nov >= 68 and con >= 58:
                    return "highlight"
                if nov >= 74:
                    return "quirky"
                if tr >= TREND_THRESHOLD and sn < 0.55:
                    return "new"
                if sn >= 0.65:
                    return "hot"
                return "regular"

            buckets: dict[str, list[SelectionDidadogProduct]] = {k: [] for k in TIER_DEFS}
            for p in eligible:
                buckets[_classify(p)].append(p)

            def _title_sim(a: str, b: str) -> float:
                a0, b0 = a or "", b or ""
                if not a0 or not b0:
                    return 0.0
                return difflib.SequenceMatcher(None, a0, b0).ratio()

            chosen_ids: set[int] = set()

            def _pick(pool: list[SelectionDidadogProduct], key, n: int, diversity: bool = False) -> list[SelectionDidadogProduct]:
                out: list[SelectionDidadogProduct] = []
                for p in sorted(pool, key=key):
                    if p.id in chosen_ids:
                        continue
                    if diversity and any(_title_sim(p.title, c.title) > 0.62 for c in out):
                        continue
                    out.append(p)
                    chosen_ids.add(p.id)
                    if len(out) >= n:
                        break
                return out

            # 每类配额 2 款，共 10；亮点要求标题去重（diversity）
            QUOTA = {"highlight": 2, "quirky": 2, "new": 2, "hot": 2, "regular": 2}
            within_key: dict[str, Any] = {
                "highlight": lambda p: (-(scores[p.id]["novelty"] + scores[p.id]["content"]), p.id),
                "quirky": lambda p: (-scores[p.id]["novelty"], p.id),
                "new": lambda p: (-_trend_score(p.title, p.category, now), p.id),
                "hot": lambda p: (-int(p.sales_count or 0), p.id),
                "regular": lambda p: (-int(p.sales_count or 0), p.id),
            }
            for tier in ["highlight", "quirky", "new", "hot", "regular"]:
                _pick(buckets[tier], within_key[tier], QUOTA[tier], diversity=(tier == "highlight"))

            # 缺口补齐：剩余候选按综合分排序，分类取其本身分层（兜底常规）
            if len(chosen_ids) < 10:
                remain = [p for p in eligible if p.id not in chosen_ids]
                remain.sort(key=lambda p: (
                    -(scores[p.id]["novelty"] + scores[p.id]["content"] + _trend_score(p.title, p.category, now) * 2 + _sales_norm(p) * 30),
                    p.id,
                ))
                for p in remain:
                    if len(chosen_ids) >= 10:
                        break
                    chosen_ids.add(p.id)

            for p in eligible:
                if p.id not in chosen_ids:
                    continue
                tier = _classify(p)
                reason = TIER_REASON[tier]
                if not reason:
                    reason = (scores.get(p.id, {}).get("reason") or "差异化+内容友好，TikTok 易出圈")
                _write_selection_meta(p, tier=tier, reason=reason)

            for product in eligible:
                product.selection_status = "final" if product.id in chosen_ids else "candidate"
            task.final_count = len(chosen_ids)
            db.commit()

            # 组合分布（用于报告体现多元组合）
            tier_counts: dict[str, int] = {}
            for p in eligible:
                if p.id in chosen_ids:
                    t = _classify(p)
                    tier_counts[t] = tier_counts.get(t, 0) + 1
            portfolio_hint = "；".join(
                f"{TIER_DEFS[t]}{tier_counts.get(t, 0)}款"
                for t in ["hot", "regular", "new", "quirky", "highlight"]
                if tier_counts.get(t, 0)
            )
            update_pipeline_stage(db, task, stage="final_selection", progress=98, message="最终商品已确定，正在请求 general 大模型生成完整市场报告")
            report_candidates = [item for item in candidates if item.selection_status == "candidate"]
            report_finals = [item for item in candidates if item.selection_status == "final"]
            report_analysis = _generate_report_analysis(db, task, report_candidates, report_finals, portfolio_hint=portfolio_hint)
            task.status = "success"
            task.current_stage = "final_selection"
            task.stage_progress = 100
            task.finished_at = datetime.utcnow()
            task.result_snapshot = json.dumps({"targets": _pipeline_targets(keyword_limit, supplier_page_size, seed_per_keyword), "test_mode": test_mode, "message": "已完成选品流程和市场报告分析", "report_analysis": report_analysis}, ensure_ascii=False)
            db.commit()
            # 衍生任务只生成结果，必须由用户在“查看衍生品”弹窗中主动加入选品库。
            # 智能选品任务保留候选品/精选品自动入库逻辑。
            if task.pipeline_mode != "derivation":
                try:
                    _auto_add_selected_products_to_library(db, task, report_analysis)
                except Exception as exc:
                    # 自动入库失败不应影响任务成功状态，只记录日志
                    print(f"[selection_pipeline] 自动入库失败 task={task.id}: {exc}")
        except Exception as exc:
            _write_error(db, task, str(exc))
