from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ThirdPartyConfig


class Supplier1688Error(RuntimeError):
    pass


DEFAULT_OPTIONS = {
    "search_path": "/search",
    "method": "POST",
    "keyword_field": "keyword",
    "page_field": "page",
    "page_size_field": "page_size",
    "items_path": "data.items",
    "total_path": "data.total",
}


def get_1688_api_config(db: Session) -> ThirdPartyConfig:
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "1688_api", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    if not config:
        raise Supplier1688Error("未找到启用的 1688 API 配置，请先在第三方 API 页面新增 service_type=1688_api 的配置。")
    if not config.api_base_url:
        raise Supplier1688Error("1688 API 配置缺少 API 地址。")
    return config


def adapter_options(config: ThirdPartyConfig) -> dict[str, Any]:
    options = dict(DEFAULT_OPTIONS)
    if not config.remark:
        return options
    try:
        raw = json.loads(config.remark)
    except json.JSONDecodeError:
        return options
    if isinstance(raw, dict):
        options.update({key: value for key, value in raw.items() if value is not None})
    return options


def nested_value(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part, default)
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return default
            continue
        return default
    return current


def pick_value(data: dict[str, Any], keys: list[str], default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def normalize_supplier_product(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw_data": item}
    return {
        "supplier_product_id": str(
            pick_value(item, ["supplier_product_id", "offer_id", "offerId", "item_id", "itemId", "id"], "")
        ),
        "title": str(pick_value(item, ["title", "subject", "name", "product_name", "productName"], "")),
        "image_url": str(pick_value(item, ["image_url", "imageUrl", "main_image", "mainImage", "pic_url", "picUrl"], "")),
        "price": pick_value(item, ["price", "sale_price", "salePrice", "price_info", "priceInfo"], 0),
        "sales_count": pick_value(item, ["sales_count", "salesCount", "sold_count", "soldCount", "month_sold"], 0),
        "shop_name": str(pick_value(item, ["shop_name", "shopName", "seller_name", "sellerName", "company_name"], "")),
        "source_url": str(pick_value(item, ["source_url", "url", "detail_url", "detailUrl", "product_url"], "")),
        "raw_data": item,
    }


def extract_items(raw: Any, options: dict[str, Any]) -> tuple[list[Any], int | None]:
    if isinstance(raw, list):
        return raw, None
    if not isinstance(raw, dict):
        return [], None

    candidates = [
        nested_value(raw, str(options.get("items_path") or "")),
        raw.get("items"),
        raw.get("list"),
        nested_value(raw, "data.list"),
        nested_value(raw, "data.records"),
        nested_value(raw, "result.items"),
        nested_value(raw, "result.list"),
    ]
    items = next((value for value in candidates if isinstance(value, list)), [])
    total_value = nested_value(raw, str(options.get("total_path") or ""), None)
    if total_value is None:
        total_value = pick_value(raw, ["total", "count"], None)
    try:
        total = int(total_value) if total_value is not None else None
    except (TypeError, ValueError):
        total = None
    return items, total


def search_1688_products(db: Session, keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    keyword = keyword.strip()
    if not keyword:
        raise Supplier1688Error("搜索关键词不能为空。")

    config = get_1688_api_config(db)
    options = adapter_options(config)
    method = str(options.get("method") or "POST").upper()
    url = urljoin(config.api_base_url.rstrip("/") + "/", str(options.get("search_path") or "/search").lstrip("/"))

    payload = {
        str(options.get("keyword_field") or "keyword"): keyword,
        str(options.get("page_field") or "page"): page,
        str(options.get("page_size_field") or "page_size"): page_size,
    }
    headers = {"Content-Type": "application/json"}
    if config.access_key_encrypted:
        headers["Authorization"] = f"Bearer {config.access_key_encrypted}"
        headers["X-API-Key"] = config.access_key_encrypted
    if config.secret_key_encrypted:
        headers["X-API-Secret"] = config.secret_key_encrypted

    try:
        if method == "GET":
            response = requests.get(url, params=payload, headers=headers, timeout=20)
        else:
            response = requests.request(method, url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        raw = response.json()
    except requests.RequestException as exc:
        raise Supplier1688Error(f"1688 API 请求失败：{exc}") from exc
    except ValueError as exc:
        raise Supplier1688Error("1688 API 返回内容不是 JSON。") from exc

    items, total = extract_items(raw, options)
    return {
        "ok": True,
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [normalize_supplier_product(item) for item in items],
        "adapter": {
            "config_id": config.id,
            "config_name": config.config_name,
            "method": method,
            "search_path": options.get("search_path"),
        },
    }
