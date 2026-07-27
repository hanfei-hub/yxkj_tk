from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.models.entities import ThirdPartyConfig


DEFAULT_MIAOSHOU_API_BASE_URL = "https://openapi-erp.91miaoshou.com"
MIAOSHOU_SERVICE_TYPE = "miaoshou_api"
MIAOSHOU_DOUBAO_AI_NAME = "douBao1.6"


class MiaoshouOpenApiError(RuntimeError):
    pass


def _retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _canonical_body(payload: Any) -> str:
    if payload in (None, "", {}):
        return ""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sign(app_secret: str, path: str, timestamp: int, app_key: str, body_json: str) -> str:
    content = f"{app_secret}{path}{timestamp}{app_key}{body_json}{app_secret}"
    return hmac.new(app_secret.encode("utf-8"), content.encode("utf-8"), hashlib.sha256).hexdigest()


def _first_nonempty_str(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _extract_first_image_url(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        for item in payload:
            found = _extract_first_image_url(item)
            if found:
                return found
        return ""
    if isinstance(payload, dict):
        for key in ("newImageUrl", "imageUrl", "url", "translatedImageUrl", "resultUrl", "downloadUrl"):
            text = str(payload.get(key) or "").strip()
            if text:
                return text
        for value in payload.values():
            found = _extract_first_image_url(value)
            if found:
                return found
    return ""


def _extract_list(payload: Any, *keys: str) -> list[Any]:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    return current if isinstance(current, list) else []


def load_miaoshou_api_config(db: Session) -> tuple[str, str, str]:
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == MIAOSHOU_SERVICE_TYPE, ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    app_key = os.getenv("MIAOSHOU_APP_KEY", "").strip()
    app_secret = os.getenv("MIAOSHOU_APP_SECRET", "").strip()
    base_url = os.getenv("MIAOSHOU_API_BASE_URL", DEFAULT_MIAOSHOU_API_BASE_URL).strip() or DEFAULT_MIAOSHOU_API_BASE_URL
    if config:
        app_key = str(config.access_key_encrypted or app_key).strip()
        app_secret = str(config.secret_key_encrypted or app_secret).strip()
        base_url = str(config.api_base_url or base_url).strip() or DEFAULT_MIAOSHOU_API_BASE_URL
    if not app_key or not app_secret:
        raise MiaoshouOpenApiError("请先在第三方 API 配置中填写 miaoshou_api 的 AppKey 和 AppSecret。")
    return app_key, app_secret, base_url.rstrip("/")


def load_miaoshou_api_config_optional(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        return load_miaoshou_api_config(db)
    app_key = os.getenv("MIAOSHOU_APP_KEY", "").strip()
    app_secret = os.getenv("MIAOSHOU_APP_SECRET", "").strip()
    base_url = os.getenv("MIAOSHOU_API_BASE_URL", DEFAULT_MIAOSHOU_API_BASE_URL).strip() or DEFAULT_MIAOSHOU_API_BASE_URL
    if not app_key or not app_secret:
        try:
            from app.core.database import SessionLocal
        except Exception as exc:
            raise MiaoshouOpenApiError("请先配置 MIAOSHOU_APP_KEY 和 MIAOSHOU_APP_SECRET。") from exc
        db = SessionLocal()
        try:
            return load_miaoshou_api_config(db)
        finally:
            db.close()
    return app_key, app_secret, base_url.rstrip("/")


class MiaoshouOpenApiClient:
    def __init__(self, app_key: str, app_secret: str, base_url: str) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._session = _retry_session()

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = _canonical_body(payload or {})
        timestamp = int(time.time())
        sign = _sign(self.app_secret, path, timestamp, self.app_key, body)
        try:
            response = self._session.post(
                f"{self.base_url}{path}",
                data=body if body else None,
                headers={
                    "Content-Type": "application/json",
                    "x-app-key": self.app_key,
                    "x-timestamp": str(timestamp),
                    "x-sign": sign,
                },
                timeout=(15, 180),
            )
        except requests.Timeout as exc:
            raise MiaoshouOpenApiError("妙手接口请求超时，请稍后重试。") from exc
        except requests.RequestException as exc:
            raise MiaoshouOpenApiError(f"妙手接口请求失败：{exc}") from exc
        try:
            data = response.json()
        except Exception as exc:
            raise MiaoshouOpenApiError(f"妙手接口返回非 JSON 响应：{response.text[:500]}") from exc
        if response.status_code >= 400:
            message = ""
            if isinstance(data, dict):
                message = str(data.get("message") or data.get("msg") or "")
            raise MiaoshouOpenApiError(message or f"妙手接口请求失败：HTTP {response.status_code}")
        if not isinstance(data, dict):
            raise MiaoshouOpenApiError("妙手接口响应格式错误。")
        if str(data.get("result") or "").lower() not in {"success", "ok"}:
            message = str(data.get("message") or data.get("msg") or data.get("code") or "妙手接口返回失败。")
            raise MiaoshouOpenApiError(message)
        return data

    def fetch_source_links(self, collect_links: list[str]) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/common_collect_box/common_collect_box/fetch_item",
            {"collectLinks": collect_links},
        )

    def claim_to_platform_collect_box(self, detail_ids: list[int], platform: str = "tiktok", serial_number: int = 1) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/common_collect_box/common_collect_box/claimed",
            {
                "detailSerialNumberPlatformList": [
                    {"detailId": int(detail_id), "platform": platform, "serialNumber": serial_number}
                    for detail_id in detail_ids
                ]
            },
        )

    def get_shop_list(self, platform: str, site: str, page_no: int = 1, page_size: int = 100) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/shop/shop/get_shop_list",
            {"platform": platform, "site": site, "pageNo": page_no, "pageSize": page_size},
        )

    def get_tiktok_category_tree(self, site: str) -> dict[str, Any]:
        return self.post("/open/v1/product/collect_box/tiktok/collect_box/get_category_tree_by_site", {"site": site})

    def get_tiktok_category_metadata(self, site: str, cid: int, shop_ids: list[int] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"cid": int(cid)}
        if site:
            payload["site"] = site
        if shop_ids:
            payload["shopIds"] = [int(item) for item in shop_ids]
        return self.post("/open/v1/product/collect_box/tiktok/collect_box/get_category_metadata", payload)

    def get_tiktok_shop_warehouse_list(self, shop_ids: list[int]) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/get_shop_warehouse_list",
            {"shopIds": [int(item) for item in shop_ids]},
        )

    def get_tiktok_manufacturer_list(self, shop_id: int, refresh: int = 0) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/get_manufacturer_list",
            {"shopId": int(shop_id), "refresh": int(refresh)},
        )

    def get_tiktok_responsible_person_list(self, shop_id: int, refresh: int = 0) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/get_responsible_person_list",
            {"shopId": int(shop_id), "refresh": int(refresh)},
        )

    def get_tiktok_collect_box_list(self, page_no: int = 1, page_size: int = 20, status: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"pageNo": int(page_no), "pageSize": int(page_size)}
        if status:
            payload["filter"] = {"status": status}
        return self.post("/open/v1/product/collect_box/tiktok/collect_box/search_collect_box_detail_list", payload)

    def get_common_collect_box_list(self, page_no: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/common_collect_box/common_collect_box/get_common_collect_box_list",
            {"pageNo": int(page_no), "pageSize": int(page_size)},
        )

    def get_tiktok_shop_collect_item_info(self, detail_id: int, shop_id: int) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/get_shop_collect_item_info",
            {"detailId": int(detail_id), "shopId": int(shop_id)},
        )

    def get_tiktok_site_collect_item_info(self, detail_id: int, site: str) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/get_site_collect_item_info",
            {"detailId": int(detail_id), "site": site},
        )

    def save_tiktok_shop_collect_item_info(
        self,
        detail_id: int,
        shop_id: int,
        oss_md5: str,
        shop_collect_item_info: dict[str, Any],
    ) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/save_shop_collect_item_info",
            {
                "ossMd5": oss_md5,
                "detailId": int(detail_id),
                "shopId": int(shop_id),
                "shopCollectItemInfo": shop_collect_item_info,
            },
        )

    def save_tiktok_site_collect_item_info(
        self,
        detail_id: int,
        site: str,
        oss_md5: str,
        site_collect_item_info: dict[str, Any],
    ) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/save_site_collect_item_info",
            {
                "ossMd5": oss_md5,
                "site": site,
                "detailId": int(detail_id),
                "siteCollectItemInfo": site_collect_item_info,
            },
        )

    def publish_tiktok_products(self, shop_ids: list[int], detail_ids: list[int]) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/collect_box/tiktok/collect_box/save_move_collect_task",
            {"shopIds": [int(item) for item in shop_ids], "detailIds": [int(item) for item in detail_ids]},
        )

    def translate_image(
        self,
        image_urls: list[str],
        source_lang: str,
        target_lang: str,
        translate_platform: str,
        no_translate_image_text_options: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "imageUrls": [str(item).strip() for item in image_urls if str(item).strip()],
            "sourceLang": source_lang,
            "targetLang": target_lang,
            "translatePlatform": translate_platform,
        }
        if no_translate_image_text_options:
            payload["noTranslateImageTextOptions"] = [
                str(item).strip() for item in no_translate_image_text_options if str(item).strip()
            ]
        return self.post("/open/v1/product/common/translate/translate_image", payload)

    def remove_image(
        self,
        image_urls: list[str],
        trace_info: dict[str, Any],
        remove_config: dict[str, Any],
    ) -> dict[str, Any]:
        return self.post(
            "/open/v1/product/common/image_removal/remove_image",
            {
                "imageUrls": [str(item).strip() for item in image_urls if str(item).strip()],
                "traceInfo": trace_info,
                "removeConfig": remove_config,
            },
        )

    def generate_product_info(
        self,
        *,
        generate_type_list: list[str],
        function_module: str,
        platform: str,
        ai_name: str,
        title: str,
        language_name: str,
        function_module_product_id: int | None = None,
        original_content: str = "",
        title_length_limit: int | None = None,
        keywords_list: list[str] | None = None,
        negative_words_list: list[str] | None = None,
        category_name: str = "",
        site: str = "",
        cid: str = "",
        image_info_list: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "generateTypeList": [str(item).strip() for item in generate_type_list if str(item).strip()],
            "functionModule": function_module,
            "platform": platform,
            "aiName": ai_name,
            "title": title,
            "languageName": language_name,
        }
        if function_module_product_id is not None:
            payload["functionModuleProductId"] = int(function_module_product_id)
        if original_content:
            payload["originalContent"] = original_content
        if title_length_limit is not None:
            payload["titleLengthLimit"] = int(title_length_limit)
        if keywords_list:
            payload["keywordsList"] = [str(item).strip() for item in keywords_list if str(item).strip()]
        if negative_words_list:
            payload["negativeWordsList"] = [str(item).strip() for item in negative_words_list if str(item).strip()]
        if category_name:
            payload["categoryName"] = category_name
        if site:
            payload["site"] = site
        if cid:
            payload["cid"] = cid
        if image_info_list:
            payload["imageInfoList"] = image_info_list
        return self.post("/open/v1/product/common/open_ai/generate_product_info", payload)

    def generate_sku_spec_name(
        self,
        *,
        platform: str,
        title: str,
        ai_name: str,
        language_name: str,
        function_module: str,
        sku_property_list: list[dict[str, Any]],
        product_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "platform": platform,
            "title": title,
            "aiName": ai_name,
            "languageName": language_name,
            "functionModule": function_module,
            "skuPropertyList": sku_property_list,
        }
        if product_id is not None:
            payload["productId"] = int(product_id)
        return self.post("/open/v1/product/common/open_ai/generate_sku_spec_name", payload)


def get_miaoshou_openapi_client(db: Session) -> MiaoshouOpenApiClient:
    app_key, app_secret, base_url = load_miaoshou_api_config(db)
    return MiaoshouOpenApiClient(app_key, app_secret, base_url)


def get_miaoshou_openapi_client_optional(db: Session | None = None) -> MiaoshouOpenApiClient:
    app_key, app_secret, base_url = load_miaoshou_api_config_optional(db)
    return MiaoshouOpenApiClient(app_key, app_secret, base_url)


def get_miaoshou_openapi_client_from_credentials(
    app_key: str,
    app_secret: str,
    base_url: str = "",
) -> MiaoshouOpenApiClient:
    key = str(app_key or "").strip()
    secret = str(app_secret or "").strip()
    if not key or not secret:
        raise MiaoshouOpenApiError("请先填写妙手 AppKey 和 AppSecret。")
    endpoint = str(base_url or DEFAULT_MIAOSHOU_API_BASE_URL).strip() or DEFAULT_MIAOSHOU_API_BASE_URL
    return MiaoshouOpenApiClient(key, secret, endpoint.rstrip("/"))
