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
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    TeacherReviewRecord,
    ThirdPartyConfig,
)
from app.services.ai_model_service import get_default_model_config


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


def request_new_listed(config: ThirdPartyConfig, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    token = config.access_key_encrypted or config.secret_key_encrypted
    base_url = (config.api_base_url or FASTMOSS_BASE_URL).rstrip("/")
    request_date = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
    extra_config = parse_extra_config(config.remark)
    request_date = str(extra_config.get("date") or extra_config.get("rank_date") or request_date)
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
        raise FastMossError(f"FastMoss 请求失败：HTTP {response.status_code} {response.text[:300]}")
    try:
        data = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FastMossError("FastMoss 返回不是合法 JSON。") from exc
    if isinstance(data, dict) and data.get("code") not in (0, "0", None):
        detail = data.get("message") or data.get("msg") or data.get("data") or "未知错误"
        raise FastMossError(f"FastMoss 业务请求失败：{detail}")
    if isinstance(data, dict) and isinstance(data.get("data"), str):
        raise FastMossError(f"FastMoss 业务请求失败：{data.get('data')}")
    return {"request": payload, "response": data}


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
    config = get_default_model_config(db)
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


def parse_shop_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""


def clear_old_fastmoss_products(db: Session) -> None:
    product_ids = list(
        db.scalars(select(FmProduct.id).where(FmProduct.platform == "TikTok", FmProduct.list_type == "new")).all()
    )
    if not product_ids:
        return
    recommendation_ids = list(
        db.scalars(
            select(DerivedProductRecommendation.id).where(DerivedProductRecommendation.source_product_id.in_(product_ids))
        ).all()
    )
    if recommendation_ids:
        db.execute(delete(DerivedProductAttributeScore).where(DerivedProductAttributeScore.recommendation_id.in_(recommendation_ids)))
        db.execute(delete(TeacherReviewRecord).where(TeacherReviewRecord.recommendation_id.in_(recommendation_ids)))
        db.execute(delete(DerivedProductRecommendation).where(DerivedProductRecommendation.id.in_(recommendation_ids)))
    db.execute(delete(DailyRecommendation).where(DailyRecommendation.source_product_id.in_(product_ids)))
    db.execute(delete(FmProduct).where(FmProduct.id.in_(product_ids)))


def upsert_new_listed_products(db: Session, raw: dict[str, Any]) -> dict[str, int]:
    items = extract_items(raw)
    request_date = str(raw.get("request", {}).get("filter", {}).get("date_info", {}).get("value", ""))
    clear_old_fastmoss_products(db)
    count = 0
    translation_success_count = 0
    translation_failed_count = 0
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
        translated_title = translate_to_chinese(db, original_title)
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
        product.category = translate_category(parse_category(pick_value(item, ["category", "category_name", "cate_name"], "")))
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
