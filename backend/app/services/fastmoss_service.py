from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

import requests
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    DailyRecommendation,
    DerivedProductDimensionReport,
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    TeacherReviewRecord,
    ThirdPartyConfig,
)
from app.services.ai_model_service import (
    MODEL_TYPE_TEXT_TRANSLATION,
    ModelCallError,
    chat_completion,
    extract_json_object,
    get_model_config,
)
from app.services.product_family_service import get_or_create_product_family


FASTMOSS_BASE_URL = "https://openapi.fastmoss.com"
NEW_LISTED_PATH = "/product/v1/rank/newListed"


class FastMossError(RuntimeError):
    pass


def get_fastmoss_config(db: Session) -> ThirdPartyConfig:
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "fastmoss", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    if not config:
        raise FastMossError("请先在第三方 API 配置中启用 FastMoss 配置。")
    token = config.access_key_encrypted or config.secret_key_encrypted
    if not token:
        raise FastMossError("FastMoss 配置缺少 token，请在 Access Key 或 Secret Key 中填写 Bearer token。")
    return config


def parse_extra_config(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def pick_value(item: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return default


def extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    response = data.get("response", data)
    candidates: list[Any] = [
        response.get("data") if isinstance(response, dict) else None,
        response.get("result") if isinstance(response, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
        if isinstance(candidate, dict):
            for key in ("list", "items", "records", "data"):
                value = candidate.get(key)
                if isinstance(value, list):
                    return value
    return []


def request_new_listed(config: ThirdPartyConfig, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    token = config.access_key_encrypted or config.secret_key_encrypted
    base_url = (config.api_base_url or FASTMOSS_BASE_URL).rstrip("/")
    extra_config = parse_extra_config(config.remark)
    configured_date = extra_config.get("date") or extra_config.get("rank_date")
    if configured_date:
        request_dates = [str(configured_date)]
    else:
        request_dates = [(date.today() - timedelta(days=days)).strftime("%Y-%m-%d") for days in range(4, 11)]

    last_raw: dict[str, Any] | None = None
    for request_date in request_dates:
        payload = {
            "filter": {
                "region": "JP",
                "date_info": {"type": "day", "value": request_date},
                "is_cross_border": 1,
                "is_fully_managed": 0,
            },
            "orderby": [{"field": "day3_units_sold", "order": "desc"}],
            "page": page,
            "pagesize": page_size,
        }
        response = requests.post(
            f"{base_url}{NEW_LISTED_PATH}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if response.status_code >= 400:
            raise FastMossError(f"FastMoss request failed: HTTP {response.status_code} {response.text[:300]}")
        try:
            data = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise FastMossError("FastMoss response is not valid JSON.") from exc
        if isinstance(data, dict) and data.get("code") not in (0, "0", None):
            detail = data.get("message") or data.get("msg") or data.get("data") or "unknown error"
            raise FastMossError(f"FastMoss business request failed: {detail}")
        if isinstance(data, dict) and isinstance(data.get("data"), str):
            raise FastMossError(f"FastMoss business request failed: {data.get('data')}")
        raw = {"request": payload, "response": data}
        last_raw = raw
        if configured_date or extract_items(raw):
            return raw
    return last_raw or {"request": {}, "response": {}}


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\ufffd", "").strip()


def parse_price(value: Any) -> float:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,.]+", str(value))
    return float(match.group(0).replace(",", "")) if match else 0


def parse_category(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    names: list[str] = []
    for key in ("l1", "l2", "l3"):
        item = value.get(key)
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return " / ".join(names)


CATEGORY_TRANSLATIONS = {
    "Toys & Hobbies": "玩具与兴趣",
    "Classic & Novelty Toys": "经典与新奇玩具",
    "Stress Relief Toys": "解压玩具",
    "Dolls & Stuffed Toys": "娃娃与毛绒玩具",
    "Dolls": "娃娃",
    "Action & Toy Figures": "手办与玩具公仔",
    "Womenswear & Underwear": "女装与内衣",
    "Women's Bottoms": "女士下装",
    "Trousers": "长裤",
    "Jewelry Accessories & Derivatives": "珠宝配饰",
    "Natural Crystal": "天然水晶",
    "Natural Crystal Decorations": "水晶摆件",
    "Tools & Hardware": "工具五金",
    "Hand Tools": "手动工具",
    "Wrenches": "扳手",
    "Fashion Accessories": "时尚配饰",
    "Costume Jewelry & Accessories": "饰品配件",
    "Bracelets & Bangles": "手链与手镯",
    "Home Supplies": "家居用品",
    "Home Decor": "家居装饰",
    "Statues & Figurines": "摆件公仔",
}


def translate_category(category: str) -> str:
    if not category:
        return ""
    parts = [part.strip() for part in category.split("/") if part.strip()]
    return " / ".join(CATEGORY_TRANSLATIONS.get(part, part) for part in parts)


def translate_to_chinese(db: Session, text: str) -> str:
    text = clean_text(text)
    if not text:
        return text
    config = get_model_config(db, MODEL_TYPE_TEXT_TRANSLATION)
    if not config:
        return text
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    payload = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": "你是电商商品标题翻译助手。只输出简体中文商品标题，不要解释。"},
            {"role": "user", "content": text[:1200]},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        translated = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return translated or text
    except requests.RequestException:
        return text


def translate_titles_to_chinese(db: Session, titles: list[str]) -> list[str]:
    titles = [clean_text(title) for title in titles]
    if not titles:
        return []
    config = get_model_config(db, MODEL_TYPE_TEXT_TRANSLATION)
    if not config:
        return titles
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    payload = {
        "model": config.model_name,
        "messages": [
            {
                "role": "system",
                "content": "Translate e-commerce product titles into concise Simplified Chinese. Return only a JSON array of strings.",
            },
            {"role": "user", "content": json.dumps(titles, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": max(800, len(titles) * 80),
    }
    if (config.provider or "").lower() == "doubao":
        payload["thinking"] = {"type": "disabled"}
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE).strip()
            content = re.sub(r"```$", "", content).strip()
        match = re.search(r"\[.*\]", content, flags=re.DOTALL)
        values = json.loads(match.group(0) if match else content)
        if isinstance(values, list) and len(values) == len(titles):
            return [clean_text(value) or original for value, original in zip(values, titles)]
    except (requests.RequestException, ValueError, TypeError):
        pass
    return titles


def translate_titles_and_family_infos(
    db: Session,
    products: list[dict[str, str]],
    task_id: int | None = None,
) -> list[dict[str, Any]]:
    if not products:
        return []
    fallback = [
        {
            "translated_title": clean_text(item.get("title")),
            "family_group": "",
            "family_variant": "",
            "family_name": "",
            "normalized_keywords": [],
            "match_rule": "",
        }
        for item in products
    ]
    prompt = {
        "task": "FastMoss商品标题翻译和标准化商品分族信息提取",
        "rules": [
            "先把商品标题翻译成简体中文。",
            "再根据中文标题和类目，提取标准化商品族信息。",
            "你只负责给出商品族信息，不判断是否新建商品族。",
            "是否新建商品族由后端根据 family_group 查询 product_families 决定。",
            "family_group 表示可长期复用的核心商品方向，不能太粗，也不能按单个造型过细。",
            "family_variant 表示造型、材质、规格、人群或使用场景等变体。",
            "例如：会爬会动的螃蟹电动感应儿童玩具，family_group 应类似 电动感应爬行动物玩具，螃蟹造型放入 family_variant。",
            "不要因为颜色、数量、单个造型不同改变 family_group。",
            "normalized_keywords 输出适合后端相似匹配和后续检索的中文关键词。",
            "所有输出必须是简体中文。",
        ],
        "products": products,
        "output_schema": [
            {
                "translated_title": "中文商品标题",
                "family_group": "稳定商品族",
                "family_variant": "商品变体",
                "family_name": "展示名称",
                "normalized_keywords": ["关键词1", "关键词2"],
                "match_rule": "一句话说明分族依据",
            }
        ],
    }
    try:
        answer = chat_completion(
            db,
            [
                {"role": "system", "content": "你是电商商品翻译和商品分族信息提取专家。只输出合法JSON数组。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            model_type=MODEL_TYPE_TEXT_TRANSLATION,
            task_id=task_id,
            temperature=0.1,
            max_tokens=max(1200, len(products) * 260),
        )
        parsed = extract_json_object(answer)
    except ModelCallError:
        return fallback
    if not isinstance(parsed, list) or len(parsed) != len(products):
        return fallback

    result: list[dict[str, Any]] = []
    for raw, original in zip(parsed, fallback):
        if not isinstance(raw, dict):
            result.append(original)
            continue
        keywords = raw.get("normalized_keywords") or raw.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        result.append(
            {
                "translated_title": clean_text(raw.get("translated_title")) or original["translated_title"],
                "family_group": clean_text(raw.get("family_group")),
                "family_variant": clean_text(raw.get("family_variant")),
                "family_name": clean_text(raw.get("family_name")),
                "normalized_keywords": [clean_text(item) for item in keywords if clean_text(item)],
                "match_rule": clean_text(raw.get("match_rule")),
            }
        )
    return result


def parse_shop_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""


def clear_old_fastmoss_products(db: Session) -> None:
    recommendation_ids = list(
        db.scalars(select(DerivedProductRecommendation.id)).all()
    )
    if recommendation_ids:
        db.execute(delete(DerivedProductDimensionReport).where(DerivedProductDimensionReport.recommendation_id.in_(recommendation_ids)))
        db.execute(delete(DerivedProductAttributeScore).where(DerivedProductAttributeScore.recommendation_id.in_(recommendation_ids)))
        db.execute(delete(TeacherReviewRecord).where(TeacherReviewRecord.recommendation_id.in_(recommendation_ids)))
    db.execute(delete(DailyRecommendation))
    db.execute(delete(DerivedProductRecommendation))
    db.execute(delete(FmProduct))


def upsert_new_listed_products(db: Session, raw: dict[str, Any], task_id: int | None = None) -> dict[str, int]:
    items = extract_items(raw)
    request_date = str(raw.get("request", {}).get("filter", {}).get("date_info", {}).get("value", ""))
    count = 0
    translation_success_count = 0
    translation_failed_count = 0
    if not items:
        return {
            "requested_count": 0,
            "synced_count": 0,
            "translation_success_count": 0,
            "translation_failed_count": 0,
        }
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return {
            "requested_count": 0,
            "synced_count": 0,
            "translation_success_count": 0,
            "translation_failed_count": 0,
        }
    original_titles = [
        clean_text(pick_value(item, ["title", "product_title", "name", "productName"], ""))
        for item in items
    ]
    categories = [
        translate_category(parse_category(pick_value(item, ["category", "category_name", "cate_name"], "")))
        for item in items
    ]
    title_family_infos = translate_titles_and_family_infos(
        db,
        [
            {"title": title, "category": category}
            for title, category in zip(original_titles, categories)
        ],
        task_id=task_id,
    )
    clear_old_fastmoss_products(db)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        external_id = str(
            pick_value(item, ["product_id", "id", "goods_id", "item_id", "productId"], f"fastmoss_{request_date}_{index}")
        )
        original_title = clean_text(pick_value(item, ["title", "product_title", "name", "productName"], "未命名商品"))
        product = FmProduct(fm_product_id=external_id)
        db.add(product)
        product.region = "JP"
        product.platform = "TikTok"
        product.list_type = "new"
        title_family_info = title_family_infos[index - 1] if index - 1 < len(title_family_infos) else {}
        translated_title = clean_text(title_family_info.get("translated_title")) or original_title
        product.title = translated_title
        if translated_title and translated_title != original_title:
            translation_success_count += 1
        else:
            translation_failed_count += 1
        product.image_url = clean_text(pick_value(item, ["image_url", "cover", "img", "image", "product_image"], ""))
        product.price = parse_price(pick_value(item, ["price", "real_price", "sale_price", "product_price"], 0))
        product.currency = "JPY"
        product.sales_count = int(
            float(
                pick_value(
                    item,
                    ["sales_count", "sales", "sale_count", "volume", "day3_units_sold", "total_units_sold"],
                    0,
                )
                or 0
            )
        )
        product.rank_no = int(float(pick_value(item, ["rank_no", "rank", "ranking"], index) or index))
        product.category = categories[index - 1] if index - 1 < len(categories) else ""
        family = get_or_create_product_family(
            db,
            title=product.title,
            category=product.category,
            family_info=title_family_info,
        )
        product.family_id = family.id
        product.shop_name = parse_shop_name(pick_value(item, ["shop", "shop_name", "seller_name", "store_name"], ""))
        product.comment_count = int(float(pick_value(item, ["comment_count", "comments", "review_count"], 0) or 0))
        product.source_url = clean_text(pick_value(item, ["source_url", "url", "product_url"], ""))
        product.data_date = request_date
        product.raw_data = json.dumps({"original_title": original_title, "fastmoss": item}, ensure_ascii=False)
        count += 1
    db.commit()
    return {
        "requested_count": len(items),
        "synced_count": count,
        "translation_success_count": translation_success_count,
        "translation_failed_count": translation_failed_count,
    }

