from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DerivedProductRecommendation, ThirdPartyConfig
from app.services.ai_model_service import MODEL_TYPE_PRODUCT_VISION, ModelCallError, chat_completion, extract_json_object


class Supplier1688Error(RuntimeError):
    pass


DEFAULT_OPTIONS = {
    "search_path": "/search",
    "method": "POST",
    "auth_mode": "headers",
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


def onebound_detail_url(item_id: Any) -> str:
    item_id = str(item_id or "").strip()
    if not item_id:
        return ""
    return f"https://detail.1688.com/offer/{item_id}.html"


def normalize_supplier_product(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"raw_data": item}
    supplier_product_id = str(
        pick_value(item, ["supplier_product_id", "offer_id", "offerId", "item_id", "itemId", "num_iid", "id"], "")
    )
    source_url = str(pick_value(item, ["source_url", "url", "detail_url", "detailUrl", "product_url"], ""))
    if not source_url:
        source_url = onebound_detail_url(supplier_product_id)
    return {
        "supplier_product_id": supplier_product_id,
        "title": str(pick_value(item, ["title", "subject", "name", "product_name", "productName"], "")),
        "image_url": str(pick_value(item, ["image_url", "imageUrl", "main_image", "mainImage", "pic_url", "picUrl"], "")),
        "price": pick_value(item, ["price", "promotion_price", "sale_price", "salePrice", "price_info", "priceInfo"], 0),
        "sales_count": pick_value(item, ["sales_count", "salesCount", "sales", "sold_count", "soldCount", "month_sold"], 0),
        "shop_name": str(pick_value(item, ["shop_name", "shopName", "seller_name", "sellerName", "nick", "company_name"], "")),
        "source_url": source_url,
        "raw_data": item,
    }


def number_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("price", "amount", "value", "min", "minPrice"):
            if key in value:
                return number_value(value[key])
    text = str(value or "").replace(",", "")
    match = __import__("re").search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0


def int_value(value: Any) -> int:
    try:
        return int(number_value(value))
    except (TypeError, ValueError):
        return 0


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


def raise_for_supplier_error(raw: Any) -> None:
    if not isinstance(raw, dict):
        return
    success = raw.get("success")
    error = raw.get("error") or raw.get("reason") or raw.get("msg") or raw.get("message")
    error_code = raw.get("error_code") or raw.get("code")
    if success in (0, "0", False) and error:
        code_text = f"（错误码：{error_code}）" if error_code not in (None, "") else ""
        raise Supplier1688Error(f"1688 API 返回错误：{error}{code_text}")


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
    if options.get("sort"):
        payload["sort"] = options["sort"]
    if options.get("cat"):
        payload["cat"] = options["cat"]
    if options.get("filter"):
        payload["filter"] = options["filter"]
    if options.get("result_type"):
        payload["result_type"] = options["result_type"]
    if options.get("lang"):
        payload["lang"] = options["lang"]

    headers = {"Content-Type": "application/json"}
    auth_mode = str(options.get("auth_mode") or "headers").lower()
    if auth_mode == "query":
        if config.access_key_encrypted:
            payload["key"] = config.access_key_encrypted
        if config.secret_key_encrypted:
            payload["secret"] = config.secret_key_encrypted
    elif config.access_key_encrypted:
        headers["Authorization"] = f"Bearer {config.access_key_encrypted}"
        headers["X-API-Key"] = config.access_key_encrypted
    if auth_mode != "query" and config.secret_key_encrypted:
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

    raise_for_supplier_error(raw)
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


def build_match_prompt(derived: DerivedProductRecommendation, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    image_candidates = [
        {"index": index, "image_url": item.get("image_url") or ""}
        for index, item in enumerate(candidates, start=1)
        if item.get("image_url")
    ]
    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "task": "判断衍生品名称和 1688 候选商品图片的匹配度。",
                    "rules": [
                        "只根据衍生品名称和候选图片视觉内容判断，不参考 1688 标题、价格、销量、店铺。",
                        "从候选图片中选择匹配度最高的一张。",
                        "如果没有明显匹配项，best_index 返回 0。",
                        "只返回纯 JSON，不要输出 markdown 或额外解释。",
                    ],
                    "derived_product": {"title": derived.derived_title},
                    "candidates": image_candidates,
                    "output_schema": {
                        "best_index": "候选 index，无法匹配填 0",
                        "match_score": "0-100 数字，90 以上表示名称和图片高度匹配",
                        "reason": "用一句中文分析衍生品名称和图片的匹配度",
                    },
                },
                ensure_ascii=False,
            ),
        }
    ]
    for item in image_candidates:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": item["image_url"]},
            }
        )
    return [
        {
            "role": "system",
            "content": "你是 1688 货源图片匹配审核员。只根据衍生品名称和候选图片判断匹配度，只输出合法 JSON。",
        },
        {"role": "user", "content": user_content},
    ]

def score_supplier_candidates(
    db: Session,
    derived: DerivedProductRecommendation,
    candidates: list[dict[str, Any]],
    task_id: int | None = None,
) -> dict[str, Any]:
    if not candidates:
        return {"best_index": 0, "match_score": 0, "reason": "候选为空"}
    try:
        answer = chat_completion(
            db,
            build_match_prompt(derived, candidates),
            model_type=MODEL_TYPE_PRODUCT_VISION,
            task_id=task_id,
            temperature=0.1,
            max_tokens=800,
        )
        parsed = extract_json_object(answer)
    except ModelCallError as exc:
        raise Supplier1688Error(f"1688 匹配大模型调用失败：{exc}") from exc
    if not isinstance(parsed, dict):
        return {"best_index": 0, "match_score": 0, "reason": "模型返回格式不是对象"}
    try:
        best_index = int(parsed.get("best_index") or parsed.get("index") or 0)
    except (TypeError, ValueError):
        best_index = 0
    score = number_value(parsed.get("match_score") or parsed.get("score") or 0)
    return {
        "best_index": best_index,
        "match_score": max(0.0, min(100.0, score)),
        "reason": str(parsed.get("reason") or parsed.get("match_reason") or ""),
        "raw": parsed,
    }


def apply_supplier_match(
    derived: DerivedProductRecommendation,
    candidate: dict[str, Any],
    score: float,
    report: dict[str, Any],
) -> None:
    derived.supplier_product_id = str(candidate.get("supplier_product_id") or "")
    derived.supplier_title = str(candidate.get("title") or "")[:512]
    derived.supplier_image_url = str(candidate.get("image_url") or "")
    derived.supplier_price = number_value(candidate.get("price"))
    derived.supplier_sales_count = int_value(candidate.get("sales_count"))
    derived.supplier_shop_name = str(candidate.get("shop_name") or "")[:255]
    derived.supplier_source_url = str(candidate.get("source_url") or "")
    derived.supplier_match_score = score
    derived.supplier_match_report = json.dumps(report, ensure_ascii=False)
    derived.supplier_raw_data = json.dumps(candidate.get("raw_data") or candidate, ensure_ascii=False)
    derived.supplier_search_status = "matched"


def auto_match_1688_for_derived(
    db: Session,
    derived_id: int,
    *,
    threshold: float = 90,
    max_candidates: int = 200,
    page_size: int = 20,
    task_id: int | None = None,
) -> dict[str, Any]:
    derived = db.get(DerivedProductRecommendation, derived_id)
    if not derived:
        raise Supplier1688Error("衍生品不存在。")
    keyword = (derived.search_keywords or derived.derived_title or "").strip()
    if not keyword:
        raise Supplier1688Error("衍生品缺少搜索关键词。")

    threshold = max(0.0, min(100.0, float(threshold)))
    page_size = max(1, min(100, int(page_size)))
    max_candidates = max(page_size, int(max_candidates))
    searched_count = 0
    best_result: dict[str, Any] = {"match_score": 0, "best_index": 0, "reason": ""}
    best_candidate: dict[str, Any] | None = None
    page = 1

    while searched_count < max_candidates:
        result = search_1688_products(db, keyword, page=page, page_size=page_size)
        candidates = result.get("items") or []
        if not candidates:
            break
        remain = max_candidates - searched_count
        candidates = candidates[:remain]
        scored = score_supplier_candidates(db, derived, candidates, task_id=task_id)
        searched_count += len(candidates)
        best_index = int(scored.get("best_index") or 0)
        score = float(scored.get("match_score") or 0)
        if 1 <= best_index <= len(candidates) and score > float(best_result.get("match_score") or 0):
            best_result = scored
            best_candidate = candidates[best_index - 1]
        if best_candidate and score >= threshold:
            apply_supplier_match(derived, best_candidate, score, best_result)
            db.commit()
            return {
                "ok": True,
                "matched": True,
                "derived_id": derived.id,
                "keyword": keyword,
                "threshold": threshold,
                "searched_count": searched_count,
                "match_score": score,
                "item": best_candidate,
                "report": best_result,
            }
        page += 1

    derived.supplier_search_status = "no_match"
    derived.supplier_match_score = float(best_result.get("match_score") or 0)
    derived.supplier_match_report = json.dumps(best_result, ensure_ascii=False)
    db.commit()
    return {
        "ok": True,
        "matched": False,
        "derived_id": derived.id,
        "keyword": keyword,
        "threshold": threshold,
        "searched_count": searched_count,
        "best_score": derived.supplier_match_score,
        "best_item": best_candidate,
        "report": best_result,
    }


def auto_match_pending_derived_products(
    db: Session,
    *,
    limit: int = 20,
    threshold: float = 90,
    max_candidates: int = 200,
    page_size: int = 20,
    task_id: int | None = None,
) -> dict[str, Any]:
    items = db.scalars(
        select(DerivedProductRecommendation)
        .where(DerivedProductRecommendation.supplier_search_status.in_(["not_searched", "no_match", "failed"]))
        .order_by(DerivedProductRecommendation.id.asc())
        .limit(max(1, int(limit)))
    ).all()
    results: list[dict[str, Any]] = []
    matched_count = 0
    failed_count = 0
    for item in items:
        try:
            result = auto_match_1688_for_derived(
                db,
                item.id,
                threshold=threshold,
                max_candidates=max_candidates,
                page_size=page_size,
                task_id=task_id,
            )
            matched_count += 1 if result.get("matched") else 0
            results.append(result)
        except Supplier1688Error as exc:
            item.supplier_search_status = "failed"
            item.supplier_match_report = json.dumps({"error": str(exc)}, ensure_ascii=False)
            db.commit()
            failed_count += 1
            results.append({"ok": False, "derived_id": item.id, "error": str(exc)})
    return {
        "ok": True,
        "count": len(items),
        "matched_count": matched_count,
        "failed_count": failed_count,
        "results": results,
    }

