from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urljoin

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ThirdPartyConfig


ECHOTIK_SERVICE_TYPE = "echotik_api"
DEFAULT_ECHOTIK_BASE_URL = "https://open.echotik.live"
DEFAULT_ECHOTIK_OPTIONS: dict[str, Any] = {
    "photo_search_path": "/api/v3/realtime/product/photo-search",
    "photo_method": "POST",
    "photo_image_field": "image_base64",
    "photo_region": "JP",
    "detail_path": "/api/v3/echotik/product/detail",
    "detail_method": "GET",
    "detail_ids_field": "product_ids",
    "detail_ids_separator": ",",
    "detail_batch_size": 10,
    "list_path": "/api/v3/echotik/product/list",
    "list_method": "GET",
    "list_page_size": 10,
    "list_max_page_size": 10,
    "list_retry": 4,
}


class EchoTikError(RuntimeError):
    pass


def get_echotik_api_config(db: Session) -> ThirdPartyConfig:
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == ECHOTIK_SERVICE_TYPE, ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    if not config:
        raise EchoTikError("未找到启用的 EchoTik API 配置，请先在第三方 API 页面配置 echotik_api。")
    if not config.access_key_encrypted or not config.secret_key_encrypted:
        raise EchoTikError("EchoTik API 缺少用户名或密码。")
    return config


def echotik_options(config: ThirdPartyConfig) -> dict[str, Any]:
    options = dict(DEFAULT_ECHOTIK_OPTIONS)
    try:
        custom = json.loads(config.remark or "{}")
    except json.JSONDecodeError:
        custom = {}
    if isinstance(custom, dict):
        options.update({key: value for key, value in custom.items() if value is not None})
    return options


def _auth_headers(config: ThirdPartyConfig) -> dict[str, str]:
    credentials = f"{config.access_key_encrypted}:{config.secret_key_encrypted}".encode("utf-8")
    return {"Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}", "Accept": "application/json"}


def _request_json(method: str, url: str, *, headers: dict[str, str], params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
    try:
        response = requests.request(method, url, headers=headers, params=params, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise EchoTikError(f"EchoTik API 请求失败：{exc}") from exc
    except ValueError as exc:
        raise EchoTikError("EchoTik API 返回内容不是 JSON。") from exc


def search_by_image(db: Session, image_url: str) -> dict[str, Any]:
    image_url = str(image_url or "").strip()
    if not image_url:
        raise EchoTikError("以图搜款需要图片地址。")
    config = get_echotik_api_config(db)
    options = echotik_options(config)
    url = urljoin((config.api_base_url or DEFAULT_ECHOTIK_BASE_URL).rstrip("/") + "/", str(options["photo_search_path"]).lstrip("/"))
    try:
        image_response = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        image_response.raise_for_status()
        image_base64 = base64.b64encode(image_response.content).decode("ascii")
    except requests.RequestException as exc:
        raise EchoTikError(f"下载以图搜款图片失败：{exc}") from exc
    photo_params = {"region": str(options.get("photo_region") or "JP")}
    if options.get("photo_sk"):
        photo_params["sk"] = str(options["photo_sk"])
    raw = _request_json(
        str(options.get("photo_method") or "POST").upper(),
        url,
        headers={**_auth_headers(config), "Content-Type": "application/json"},
        params=photo_params,
        payload={"image_base64": image_base64},
    )
    return {"ok": True, "image_url": image_url, "product_ids": extract_product_ids(raw), "raw_data": raw}


def get_product_details(db: Session, product_ids: list[str]) -> dict[str, Any]:
    ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not ids:
        raise EchoTikError("商品详情查询至少需要一个商品 ID。")
    config = get_echotik_api_config(db)
    options = echotik_options(config)
    batch_size = min(int(options.get("detail_batch_size") or 10), 10)
    if len(ids) > batch_size:
        raise EchoTikError(f"商品详情接口每次最多查询 {batch_size} 个商品 ID。")
    url = urljoin((config.api_base_url or DEFAULT_ECHOTIK_BASE_URL).rstrip("/") + "/", str(options["detail_path"]).lstrip("/"))
    field = str(options.get("detail_ids_field") or "product_ids")
    value = str(options.get("detail_ids_separator") or ",").join(ids)
    raw = _request_json(str(options.get("detail_method") or "GET").upper(), url, headers=_auth_headers(config), params={field: value})
    return {"ok": True, "product_ids": ids, "items": extract_items(raw), "raw_data": raw}


def search_by_keyword(
    db: Session,
    keyword: str,
    region: str = "JP",
    page_num: int = 1,
    page_size: int | None = None,
) -> dict[str, Any]:
    """EchoTik 关键词商品搜索（蓝海判断用）。

    接口：GET /api/v3/echotik/product/list
    返回：{code, message, data:[商品...]}。注意：该接口不返回市场总量 total，
    仅返回当前页商品（page_size 上限 10）。
    """
    keyword = str(keyword or "").strip()
    if not keyword:
        raise EchoTikError("关键词搜索需要关键词。")
    region = str(region or "JP").strip() or "JP"
    config = get_echotik_api_config(db)
    options = echotik_options(config)
    max_ps = int(options.get("list_max_page_size") or 10)
    ps = max(1, min(int(page_size or options.get("list_page_size") or 10), max_ps))
    url = urljoin(
        (config.api_base_url or DEFAULT_ECHOTIK_BASE_URL).rstrip("/") + "/",
        str(options["list_path"]).lstrip("/"),
    )
    params = {"keyword": keyword, "region": region, "page_num": int(page_num or 1), "page_size": ps}
    retries = max(1, int(options.get("list_retry") or 4))
    raw: Any = None
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            raw = _request_json(str(options.get("list_method") or "GET").upper(), url, headers=_auth_headers(config), params=params)
            products = _extract_list_products(raw)
            if products:  # 拿到有效数据才算成功，避免空响应被误判
                return {"ok": True, "keyword": keyword, "region": region, "page_num": params["page_num"], "total": None, "products": products, "raw_data": raw}
        except (EchoTikError, ValueError) as exc:
            last_err = exc
    if raw is not None:
        products = _extract_list_products(raw)
        if products:
            return {"ok": True, "keyword": keyword, "region": region, "page_num": params["page_num"], "total": None, "products": products, "raw_data": raw}
    raise EchoTikError(f"EchoTik 关键词搜索失败（keyword={keyword}, region={region}）：{last_err or '空响应'}") from last_err


def _extract_list_products(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if not isinstance(raw, dict):
        return []
    data = raw.get("data")
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        inner = data.get("products") or data.get("list") or data.get("items") or []
        return [p for p in inner if isinstance(p, dict)] if isinstance(inner, list) else []
    return []


def extract_product_ids(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = raw.get("e_com_items") or raw.get("data") or raw.get("items") or raw.get("list") or raw.get("result") or []
        if isinstance(values, dict):
            values = values.get("e_com_items") or values.get("items") or values.get("list") or values.get("products") or []
    else:
        values = []
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            value = value.get("product_id") or value.get("productId") or value.get("productIdStr") or value.get("search_result_id") or value.get("id")
        if value not in (None, ""):
            result.append(str(value))
    return result


def extract_items(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    data = raw.get("data") or raw.get("result") or raw.get("items") or raw.get("list") or []
    if isinstance(data, dict):
        data = data.get("items") or data.get("list") or data.get("products") or []
    return data if isinstance(data, list) else []
