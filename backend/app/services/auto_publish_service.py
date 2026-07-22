from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import base64
import hashlib
import html as html_lib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore, Lock, RLock
from typing import Any, Callable
from uuid import uuid4

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from urllib3.util.retry import Retry

from app.core.database import SessionLocal
from app.models.entities import (
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    ModelConfig,
    ThirdPartyConfig,
)
from app.services.serializers import derived_to_dict, product_to_dict


RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime" / "auto_publish"
LATEST_RESULT_FILE = RUNTIME_DIR / "latest_result.json"
HISTORY_FILE = RUNTIME_DIR / "history.json"
API_USAGE_FILE = RUNTIME_DIR / "api_usage.json"
DEFAULT_TEMPLATE_PATH = Path(os.getenv("MIAOSHOU_IMPORT_TEMPLATE", r"C:\Users\Gao\Downloads\导入产品模板 (1).xls"))
DEFAULT_OXYLABS_REALTIME_URL = "https://realtime.oxylabs.io/v1/queries"
AIMEDIAKIT_IMAGE_TRANSLATE_URL = "https://mediakit.cn-beijing.volces.com/api/v1/tools-sync/translate-image-text"
AIMEDIAKIT_REMOVE_ELEMENTS_URL = "https://mediakit.cn-beijing.volces.com/api/v1/tools-sync/remove-image-elements"
DEFAULT_ASSET_BASE_URL = os.getenv("AUTO_PUBLISH_ASSET_BASE_URL", "https://120.26.207.89/auto_publish")
DEFAULT_ASSET_UPLOAD_HOST = os.getenv("AUTO_PUBLISH_UPLOAD_HOST", "120.26.207.89")
DEFAULT_ASSET_UPLOAD_USER = os.getenv("AUTO_PUBLISH_UPLOAD_USER", "root")
DEFAULT_ASSET_UPLOAD_KEY = Path(os.getenv("AUTO_PUBLISH_UPLOAD_KEY", str(RUNTIME_DIR.parent / "keys" / "yxkj.pem")))
DEFAULT_ASSET_UPLOAD_DIR = os.getenv("AUTO_PUBLISH_UPLOAD_DIR", "/var/www/html/auto_publish")
MIAOSHOU_STORAGE_STATE_PATH = RUNTIME_DIR / "miaoshou_storage_state.json"
MIAOSHOU_PICTURE_UPLOAD_URL = "https://erp.91miaoshou.com/api/picture/picture/uploadPictureFile"
LOCAL_BROWSER_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
VOLCENGINE_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_TEXT_MODELS = ("doubao-seed-2-0-lite", "doubao-seed-2-1-pro")
DOUBAO_TEXT_ENDPOINTS = ("ep-20260710160935-grs59", "ep-20260626105633-4gdhv")
DOUBAO_TRANSLATION_MODELS = ("doubao-seed-translation",)
DOUBAO_TRANSLATION_ENDPOINTS = ("ep-20260713102020-zgh99",)
MEDIAKIT_TRANSLATION_PROVIDERS = ("aimediakit", "ai_mediakit", "volcengine-mediakit", "volcengine_mediakit", "mediakit")
MEDIAKIT_TRANSLATION_ENDPOINTS = (AIMEDIAKIT_IMAGE_TRANSLATE_URL, AIMEDIAKIT_REMOVE_ELEMENTS_URL)
DOUBAO_IMAGE_MODELS = ("doubao-seedream-5-0", "doubao-seedream-5-0-pro")
DOUBAO_IMAGE_ENDPOINTS = ("ep-20260710161912-qq7gf", "ep-20260710162015-r5rv9")
MAIN_IMAGE_SIZE = (1200, 1200)
DETAIL_IMAGE_WIDTH = 1200
SEEDREAM_REQUEST_SIZE = "1920x1920"
IMAGE_PROCESS_WORKERS = max(1, int(os.getenv("AUTO_PUBLISH_IMAGE_WORKERS", "8")))
BATCH_PRODUCT_WORKERS = max(1, min(10, int(os.getenv("AUTO_PUBLISH_BATCH_WORKERS", "10"))))
AIMEDIAKIT_MAX_CONCURRENCY = max(1, min(12, int(os.getenv("AUTO_PUBLISH_MEDIAKIT_CONCURRENCY", "12"))))
AIMEDIAKIT_REQUEST_GATE = BoundedSemaphore(AIMEDIAKIT_MAX_CONCURRENCY)
API_USAGE_LOCK = Lock()
TASK_HISTORY_LOCK = RLock()
MIAOSHOU_FLOW_LOCK = Lock()
CONFIG_POOL_LOCK = Lock()
CONFIG_POOL_INDEX: dict[str, int] = {}
MAIN_IMAGE_TARGET = 5
DETAIL_IMAGE_TARGET = 9
DETAIL_IMAGE_SCAN_LIMIT = max(1, int(os.getenv("AUTO_PUBLISH_DETAIL_IMAGE_SCAN_LIMIT", "30")))
DETAIL_IMAGE_OUTPUT_LIMIT = max(1, int(os.getenv("AUTO_PUBLISH_DETAIL_IMAGE_OUTPUT_LIMIT", "15")))
DETAIL_IMAGE_LIMIT = DETAIL_IMAGE_SCAN_LIMIT
AI_IMAGE_TIMEOUT_SECONDS = max(30, int(os.getenv("AUTO_PUBLISH_AI_IMAGE_TIMEOUT", "75")))
MIAOSHOU_TASK_CREDENTIALS: dict[str, tuple[str, str]] = {}
AIMEDIAKIT_REMOVE_IMAGE_ELEMENTS_CNY_PER_1000 = float(os.getenv("AUTO_PUBLISH_COST_AIMEDIAKIT_REMOVE_PER_1000", "41.4"))
AIMEDIAKIT_TRANSLATE_IMAGE_TEXT_CNY_PER_1000 = float(os.getenv("AUTO_PUBLISH_COST_AIMEDIAKIT_TRANSLATE_PER_1000", "50"))
ARK_PROMPT_CNY_PER_MILLION = float(os.getenv("AUTO_PUBLISH_COST_ARK_PROMPT_PER_MILLION", "2.4"))
ARK_COMPLETION_CNY_PER_MILLION = float(os.getenv("AUTO_PUBLISH_COST_ARK_COMPLETION_PER_MILLION", "3"))


TARGET_LANGUAGE_META = {
    "ja": {
        "label": "日语",
        "native": "日本語",
        "market": "日本 TikTok Shop",
        "mediakit": "ja",
        "fallback_title": "便利グッズ 暮らしを整える実用アイテム",
        "standard_sku": "標準",
    },
    "en": {
        "label": "英语",
        "native": "English",
        "market": "TikTok Shop",
        "mediakit": "en",
        "fallback_title": "Practical Everyday Item Useful Lifestyle Product",
        "standard_sku": "Standard",
    },
}


def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    _ensure_runtime_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            temp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.08 * (attempt + 1))
    try:
        temp_path.unlink()
    except OSError:
        pass
    if last_error:
        raise last_error


def user_can_access_task(task: dict[str, Any] | None, user_id: int | None, role: str = "") -> bool:
    if not isinstance(task, dict):
        return False
    if role == "admin":
        return True
    created_by = task.get("created_by")
    if created_by in (None, ""):
        return True
    try:
        return int(created_by) == int(user_id or 0)
    except (TypeError, ValueError):
        return False


def miaoshou_storage_state_path_for_username(username: str) -> Path:
    account = str(username or "").strip()
    if not account:
        return MIAOSHOU_STORAGE_STATE_PATH
    digest = hashlib.sha256(account.encode("utf-8")).hexdigest()[:16]
    return RUNTIME_DIR / "miaoshou_states" / f"{digest}.json"


def miaoshou_storage_state_path_for_task(task_id: str | None = None, username: str = "") -> Path:
    if username:
        return miaoshou_storage_state_path_for_username(username)
    if task_id and task_id in MIAOSHOU_TASK_CREDENTIALS:
        return miaoshou_storage_state_path_for_username(MIAOSHOU_TASK_CREDENTIALS[task_id][0])
    return MIAOSHOU_STORAGE_STATE_PATH


def _safe_endpoint(endpoint: str) -> str:
    return re.sub(r"(api[_-]?key|access[_-]?key|secret|token)=([^&\s]+)", r"\1=***", endpoint or "", flags=re.I)


def usage_key_label(name: str = "", key: str = "", config_id: Any = None) -> str:
    key_text = str(key or "").strip()
    key_tail = key_text[-6:] if len(key_text) > 6 else key_text
    label = str(name or "").strip() or "unnamed"
    prefix = f"#{config_id} " if config_id not in (None, "") else ""
    return f"{prefix}{label} (*{key_tail})" if key_tail else f"{prefix}{label}"


def model_config_usage_meta(config: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = dict(extra or {})
    meta.setdefault(
        "key_label",
        usage_key_label(
            getattr(config, "config_name", "") or getattr(config, "provider", "") or "model_config",
            getattr(config, "api_key_encrypted", ""),
            getattr(config, "id", None),
        ),
    )
    return meta


def usage_from_response_payload(payload: Any) -> dict[str, int]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for source_key, target_key in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
    ):
        value = usage.get(source_key)
        if isinstance(value, (int, float)):
            result[target_key] = result.get(target_key, 0) + int(value)
    if "total_tokens" not in result and ("prompt_tokens" in result or "completion_tokens" in result):
        result["total_tokens"] = result.get("prompt_tokens", 0) + result.get("completion_tokens", 0)
    return result


def record_api_usage(
    task_id: str,
    *,
    provider: str,
    purpose: str,
    model: str = "",
    endpoint: str = "",
    success: bool,
    request_count: int = 1,
    image_count: int = 0,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    status_code: int | None = None,
    error: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    if not task_id:
        return
    entry: dict[str, Any] = {
        "task_id": task_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "provider": provider,
        "purpose": purpose,
        "model": model,
        "endpoint": _safe_endpoint(endpoint),
        "success": bool(success),
        "request_count": int(request_count or 1),
        "image_count": int(image_count or 0),
    }
    if prompt_tokens is not None:
        entry["prompt_tokens"] = int(prompt_tokens)
    if completion_tokens is not None:
        entry["completion_tokens"] = int(completion_tokens)
    if total_tokens is not None:
        entry["total_tokens"] = int(total_tokens)
    if status_code is not None:
        entry["status_code"] = int(status_code)
    if error:
        entry["error"] = sanitize_secret_error(str(error))[:500]
    if meta:
        entry["meta"] = meta
    with API_USAGE_LOCK:
        try:
            usage = _read_json(API_USAGE_FILE, [])
            if not isinstance(usage, list):
                usage = []
            usage.append(entry)
            _write_json(API_USAGE_FILE, usage[-5000:])
        except OSError:
            return


def estimated_cost_cny_for_usage_item(item: dict[str, Any]) -> float:
    if not item.get("success"):
        return 0.0
    purpose = str(item.get("purpose") or "")
    provider = str(item.get("provider") or "")
    request_count = max(1, int(item.get("request_count") or 1))
    image_count = int(item.get("image_count") or 0)
    charge_count = image_count or request_count
    if purpose == "aimediakit_remove_image_elements":
        return charge_count * AIMEDIAKIT_REMOVE_IMAGE_ELEMENTS_CNY_PER_1000 / 1000
    if purpose == "aimediakit_translate_image_text":
        return charge_count * AIMEDIAKIT_TRANSLATE_IMAGE_TEXT_CNY_PER_1000 / 1000
    if provider in {"volcengine_ark", "volcengine", "ark"}:
        prompt_tokens = int(item.get("prompt_tokens") or 0)
        completion_tokens = int(item.get("completion_tokens") or 0)
        return (
            prompt_tokens * ARK_PROMPT_CNY_PER_MILLION / 1_000_000
            + completion_tokens * ARK_COMPLETION_CNY_PER_MILLION / 1_000_000
        )
    return 0.0


def api_usage_for_task(task_id: str) -> dict[str, Any]:
    usage = _read_json(API_USAGE_FILE, [])
    if not isinstance(usage, list):
        usage = []
    entries = [item for item in usage if isinstance(item, dict) and item.get("task_id") == task_id]
    summary: dict[str, Any] = {
        "entries": entries,
        "totals": {
            "request_count": 0,
            "image_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "success_count": 0,
            "failure_count": 0,
            "estimated_cost_cny": 0.0,
        },
        "by_purpose": {},
        "by_model": {},
        "by_provider": {},
        "by_key": {},
    }
    for item in entries:
        request_count = int(item.get("request_count") or 0)
        image_count = int(item.get("image_count") or 0)
        prompt_tokens = int(item.get("prompt_tokens") or 0)
        completion_tokens = int(item.get("completion_tokens") or 0)
        total_tokens = int(item.get("total_tokens") or 0)
        estimated_cost_cny = estimated_cost_cny_for_usage_item(item)
        summary["totals"]["request_count"] += request_count
        summary["totals"]["image_count"] += image_count
        summary["totals"]["prompt_tokens"] += prompt_tokens
        summary["totals"]["completion_tokens"] += completion_tokens
        summary["totals"]["total_tokens"] += total_tokens
        summary["totals"]["estimated_cost_cny"] += estimated_cost_cny
        if item.get("success"):
            summary["totals"]["success_count"] += 1
        else:
            summary["totals"]["failure_count"] += 1
        for group_key, label in (
            ("by_purpose", str(item.get("purpose") or "unknown")),
            ("by_model", str(item.get("model") or item.get("provider") or "unknown")),
            ("by_provider", str(item.get("provider") or "unknown")),
            ("by_key", str((item.get("meta") or {}).get("key_label") or "unknown")),
        ):
            bucket = summary[group_key].setdefault(
                label,
                {
                    "request_count": 0,
                    "image_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "estimated_cost_cny": 0.0,
                },
            )
            bucket["request_count"] += request_count
            bucket["image_count"] += image_count
            bucket["prompt_tokens"] += prompt_tokens
            bucket["completion_tokens"] += completion_tokens
            bucket["total_tokens"] += total_tokens
            bucket["estimated_cost_cny"] += estimated_cost_cny
            if item.get("success"):
                bucket["success_count"] += 1
            else:
                bucket["failure_count"] += 1
    summary["totals"]["estimated_cost_cny"] = round(float(summary["totals"]["estimated_cost_cny"]), 6)
    for group_key in ("by_purpose", "by_model", "by_provider", "by_key"):
        for bucket in summary[group_key].values():
            bucket["estimated_cost_cny"] = round(float(bucket.get("estimated_cost_cny") or 0), 6)
    return summary


def attach_api_usage(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(task, dict):
        return task
    task_id = str(task.get("task_id") or "")
    if not task_id:
        return task
    return task | {"api_usage": api_usage_for_task(task_id)}


def list_publish_candidates(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    items = db.scalars(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.source_product).selectinload(FmProduct.derived_products),
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.review_status == "approved")
        .order_by(DerivedProductRecommendation.weighted_score.desc(), DerivedProductRecommendation.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "derived": derived_to_dict(item),
            "source_product": product_to_dict(item.source_product) if item.source_product else None,
        }
        for item in items
    ]


def empty_latest_result() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "idle",
        "message": "尚未创建自动上架任务。",
        "steps": [],
        "errors": [],
        "product_infos": [],
    }


def get_latest_result(user_id: int | None = None, role: str = "") -> dict[str, Any]:
    if user_id is not None and role != "admin":
        return next((item for item in list_history(user_id=user_id, role=role) if item), empty_latest_result())
    result = _read_json(LATEST_RESULT_FILE, empty_latest_result())
    return attach_api_usage(result) or result


def list_history(user_id: int | None = None, role: str = "") -> list[dict[str, Any]]:
    with TASK_HISTORY_LOCK:
        history = _read_json(HISTORY_FILE, [])
    if isinstance(history, list):
        items = [item for item in history if user_id is None or user_can_access_task(item, user_id, role)]
        return [attach_api_usage(item) or item for item in items]
    return []


def get_task_result(task_id: str, user_id: int | None = None, role: str = "") -> dict[str, Any] | None:
    item = next((item for item in list_history() if item.get("task_id") == task_id), None)
    if user_id is not None and not user_can_access_task(item, user_id, role):
        return None
    return attach_api_usage(item) if item else None


def mark_task_runtime_failure(task_id: str, message: str) -> dict[str, Any]:
    task = get_task_result(task_id) or {"task_id": task_id, "steps": [], "errors": []}
    steps = list(task.get("steps") or [])
    errors = list(task.get("errors") or [])
    errors.append(f"后台执行异常：{message}")
    result = task | {
        "status": "failed",
        "ok": False,
        "message": f"自动上架后台执行异常：{message}",
        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "steps": steps,
        "errors": errors,
        "progress": {
            "stage": "done",
            "current": 1,
            "total": 1,
            "message": "后台执行异常",
            "percent": 100,
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        },
    }
    _record_task(result)
    return result


def finish_failed_without_template(
    task: dict[str, Any],
    *,
    status: str,
    message: str,
    steps: list[str],
    errors: list[str],
    product_infos: list[dict[str, Any]] | None = None,
    progress_message: str = "流程已停止",
) -> dict[str, Any]:
    result = task | {
        "status": status,
        "ok": False,
        "message": message,
        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "steps": steps,
        "errors": errors,
        "product_infos": product_infos or [],
        "template_path": "",
        "import_result": None,
        "progress": {
            "stage": "done",
            "current": 1,
            "total": 1,
            "message": progress_message,
            "percent": 100,
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        },
    }
    _record_task(result)
    return result


def normalize_image_mode(value: Any) -> str:
    return "smart"


def normalize_target_language(value: Any) -> str:
    language = str(value or "ja").strip().lower()
    if language in {"jp", "jpn", "japanese", "日本語", "日语"}:
        return "ja"
    if language in {"en", "eng", "english", "英语"}:
        return "en"
    return "ja"


def target_language_meta(language: Any) -> dict[str, str]:
    return TARGET_LANGUAGE_META[normalize_target_language(language)]


def image_mode_settings(mode: str) -> dict[str, int | str]:
    return {
        "mode": "smart",
        "main_target": 5,
        "main_limit": 5,
        "detail_target": 9,
        "detail_limit": DETAIL_IMAGE_LIMIT,
        "workers": min(max(IMAGE_PROCESS_WORKERS, 6), 10),
    }


def update_task_progress(
    task_id: str,
    stage: str,
    current: int,
    total: int,
    message: str,
    percent: int | None = None,
) -> None:
    task = get_task_result(task_id)
    if not task:
        return
    safe_total = max(1, int(total or 1))
    safe_current = max(0, min(int(current or 0), safe_total))
    if percent is None:
        percent = round(safe_current / safe_total * 100)
    progress = {
        "stage": stage,
        "current": safe_current,
        "total": safe_total,
        "message": message,
        "percent": max(0, min(int(percent), 100)),
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
    }
    task = task | {"status": "running", "progress": progress}
    if message:
        steps = list(task.get("steps") or [])
        if not steps or steps[-1] != message:
            steps.append(message)
        task["steps"] = steps[-20:]
    _record_task(task)


def create_task(db: Session, payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    derived_id = int(payload.get("derived_id") or 0)
    derived = db.scalar(
        select(DerivedProductRecommendation)
        .options(
            selectinload(DerivedProductRecommendation.source_product).selectinload(FmProduct.derived_products),
            selectinload(DerivedProductRecommendation.attributes).selectinload(DerivedProductAttributeScore.attribute),
        )
        .where(DerivedProductRecommendation.id == derived_id)
    )
    if not derived:
        raise ValueError("衍生品不存在，无法创建自动上架任务。")
    if derived.review_status != "approved":
        raise ValueError("只有教师审核通过的衍生品可以进入自动上架。")

    quantity = max(1, min(int(payload.get("publish_count") or 1), 20))
    dry_run = bool(payload.get("dry_run", True))
    now = datetime.utcnow().replace(microsecond=0).isoformat()
    task = {
        "task_id": uuid4().hex,
        "created_at": now,
        "created_by": user_id,
        "status": "created",
        "dry_run": dry_run,
        "publish_count": quantity,
        "target_channel": str(payload.get("target_channel") or "TikTok Shop Japan"),
        "erp_url": str(payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270"),
        "derived": derived_to_dict(derived),
        "source_product": product_to_dict(derived.source_product) if derived.source_product else None,
        "steps": ["已创建自动上架任务，等待执行。"],
        "errors": [],
        "product_infos": [],
    }
    _record_task(task)
    return task


def run_task(task_id: str) -> dict[str, Any]:
    history = list_history()
    task = next((item for item in history if item.get("task_id") == task_id), None)
    if not task:
        raise ValueError("自动上架任务不存在。")

    title = task.get("derived", {}).get("derived_title") or "未命名商品"
    source_title = (task.get("source_product") or {}).get("title") or "未知原商品"
    product_info = {
        "title": title,
        "source_title": source_title,
        "target_channel": task.get("target_channel"),
        "suggested_price_min": task.get("derived", {}).get("suggested_price_min"),
        "suggested_price_max": task.get("derived", {}).get("suggested_price_max"),
        "search_keywords": task.get("derived", {}).get("search_keywords"),
    }

    steps = [
        f"已读取审核通过的衍生品：{title}",
        f"已生成上架草稿，目标渠道：{task.get('target_channel')}",
        "已整理标题、卖点、适用场景、风险提示和供运营复核的商品资料。",
    ]
    if task.get("dry_run", True):
        steps.append("当前为 dry-run 模式：未登录 ERP，未提交真实上架。")
        status = "draft_ready"
        ok = True
        message = "自动上架草稿已生成，可交由运营复核后接入真实 ERP 自动化。"
    else:
        steps.append("真实 ERP 自动化适配器尚未启用，本次未提交外部平台。")
        status = "adapter_not_configured"
        ok = False
        message = "已阻止真实提交：请先配置稳定的 ERP 自动化适配器。"

    result = task | {
        "status": status,
        "ok": ok,
        "message": message,
        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "steps": steps,
        "errors": [] if ok else ["ERP 自动化适配器未配置。"],
        "product_infos": [product_info],
    }
    _record_task(result)
    return result


def create_1688_publish_task(db: Session, payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    offer_url = normalize_1688_url(str(payload.get("offer_url") or ""))
    if not offer_url:
        raise ValueError("请输入有效的 1688 商品链接。")
    miaoshou_username = str(payload.get("miaoshou_username") or "").strip()
    miaoshou_password = str(payload.get("miaoshou_password") or "").strip()
    if not miaoshou_username or not miaoshou_password:
        raise ValueError("请填写妙手账号和密码。系统会自动填写账号密码，验证码由你手动完成后继续导入模板。")

    task_id = uuid4().hex
    target_language = normalize_target_language(payload.get("target_language"))
    MIAOSHOU_TASK_CREDENTIALS[task_id] = (miaoshou_username, miaoshou_password)
    task = {
        "task_id": task_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "created_by": user_id,
        "status": "created",
        "workflow": "1688_to_miaoshou",
        "dry_run": False,
        "offer_url": offer_url,
        "image_mode": "smart",
        "publish_count": 1,
        "target_channel": "TikTok Shop Japan",
        "target_language": target_language,
        "erp_url": str(payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270"),
        "steps": [
            "已创建 1688 链接自动上架任务，等待执行。",
            "本次会使用填写的妙手账号密码；不再复用旧登录态，验证码需要你在妙手窗口手动完成。",
        ],
        "errors": [],
        "product_infos": [],
    }
    _record_task(task)
    return task


def create_1688_batch_publish_task(db: Session, payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    raw_urls = payload.get("offer_urls") or []
    if not isinstance(raw_urls, list):
        raw_urls = []
    offer_urls: list[str] = []
    seen: set[str] = set()
    for raw_url in raw_urls:
        offer_url = normalize_1688_url(str(raw_url or ""))
        if offer_url and offer_url not in seen:
            seen.add(offer_url)
            offer_urls.append(offer_url)
    if not offer_urls:
        raise ValueError("请输入至少一个有效的 1688 商品链接。")
    miaoshou_username = str(payload.get("miaoshou_username") or "").strip()
    miaoshou_password = str(payload.get("miaoshou_password") or "").strip()
    if not miaoshou_username or not miaoshou_password:
        raise ValueError("请填写妙手账号和密码。系统会自动填写账号密码，验证码由你手动完成后继续导入模板。")

    task_id = uuid4().hex
    target_language = normalize_target_language(payload.get("target_language"))
    MIAOSHOU_TASK_CREDENTIALS[task_id] = (miaoshou_username, miaoshou_password)
    task = {
        "task_id": task_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "created_by": user_id,
        "status": "created",
        "workflow": "1688_batch_to_miaoshou",
        "dry_run": False,
        "offer_urls": offer_urls,
        "image_mode": "smart",
        "publish_count": len(offer_urls),
        "target_channel": "TikTok Shop Japan",
        "target_language": target_language,
        "erp_url": str(payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270"),
        "steps": [
            f"已创建批量自动上架任务，共 {len(offer_urls)} 个 1688 链接。",
            "多个商品会写入同一个妙手模板；产品主编号用于区分不同商品。",
            "妙手图片上传和模板导入阶段会串行执行，避免登录态冲突。",
        ],
        "errors": [],
        "product_infos": [],
    }
    _record_task(task)
    return task


def run_1688_publish_task(db: Session, task_id: str) -> dict[str, Any]:
    history = list_history()
    task = next((item for item in history if item.get("task_id") == task_id), None)
    if not task:
        raise ValueError("自动上架任务不存在。")
    if task.get("workflow") == "1688_batch_to_miaoshou":
        return run_1688_batch_publish_task(db, task)
    if task.get("workflow") != "1688_to_miaoshou":
        return run_task(task_id)

    steps: list[str] = []
    errors: list[str] = []
    miaoshou_lock_acquired = False

    def enter_miaoshou_stage() -> None:
        nonlocal miaoshou_lock_acquired
        if not miaoshou_lock_acquired:
            update_task_progress(task_id, "miaoshou_wait", 0, 1, "等待妙手上传/导入队列", 80)
            MIAOSHOU_FLOW_LOCK.acquire()
            miaoshou_lock_acquired = True
        try:
            ensure_miaoshou_login_state(db, task["task_id"], str(task.get("erp_url") or ""))
        except Exception:
            if miaoshou_lock_acquired:
                miaoshou_lock_acquired = False
                MIAOSHOU_FLOW_LOCK.release()
            raise

    def release_miaoshou_stage() -> None:
        nonlocal miaoshou_lock_acquired
        if miaoshou_lock_acquired:
            miaoshou_lock_acquired = False
            MIAOSHOU_FLOW_LOCK.release()

    offer_url = str(task.get("offer_url") or "")
    image_mode = normalize_image_mode(task.get("image_mode"))
    mode_settings = image_mode_settings(image_mode)
    main_target = int(mode_settings["main_target"])
    detail_target = int(mode_settings["detail_target"])
    update_task_progress(task_id, "fetch", 0, 1, "正在抓取1688数据", 5)
    try:
        raw_page = fetch_1688_page_with_oxylabs(db, offer_url, task_id=task_id)
        steps.append("已通过 Oxylabs 获取 1688 商品页数据。")
        update_task_progress(task_id, "fetch", 1, 1, "已获取1688商品数据", 18)
    except AutoPublishError as exc:
        errors.append(str(exc))
        errors.append("失败定位：Oxylabs 未成功获取 1688 商品页数据，已按要求停止流程；不会生成妙手模板，也不会自动导入妙手。")
        return finish_failed_without_template(
            task,
            status="fetch_failed",
            message="Oxylabs 获取 1688 商品失败，已停止自动上架流程。",
            steps=steps,
            errors=errors,
            progress_message="Oxylabs 获取失败，流程已停止",
        )

    product = extract_1688_product(offer_url, raw_page.get("html", ""), raw_page.get("raw", {}))
    parse_errors: list[str] = []
    if not clean_html_text(str(product.get("title") or "")):
        parse_errors.append("未能从 1688 页面解析到商品标题")
    main_source_count = len(unique_urls(product.get("main_images", []) or []))
    detail_source_count = len(unique_urls(product.get("detail_images", []) or []))
    sku_source_count = len(unique_urls([str(sku.get("image_url") or "") for sku in (product.get("skus") or []) if str(sku.get("image_url") or "").strip()]))
    if main_source_count + detail_source_count + sku_source_count < main_target:
        parse_errors.append(
            f"可补主图的源图数量不足：主图 {main_source_count} 张，SKU图 {sku_source_count} 张，详情图 {detail_source_count} 张，合计不足 {main_target} 张"
        )
    valid_skus = [sku for sku in (product.get("skus") or []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
    if not valid_skus:
        parse_errors.append("未能从 1688 页面解析到有效 SKU")
    if parse_errors:
        errors.extend(parse_errors)
        errors.append("失败定位：Oxylabs 已返回 1688 页面数据，但关键商品信息解析失败，已按要求停止流程；不会生成妙手模板，也不会自动导入妙手。")
        return finish_failed_without_template(
            task,
            status="parse_failed",
            message="1688 商品数据解析失败，已停止自动上架流程。",
            steps=steps,
            errors=errors,
            product_infos=[product],
            progress_message="1688 解析失败，流程已停止",
        )
    steps.append(f"已解析 1688 商品：{product['title']}")

    update_task_progress(task_id, "copy", 0, 1, "正在优化标题/SKU/描述", 24)
    try:
        optimized = optimize_for_japan_listing(
            db,
            product,
            task["task_id"],
            target_language=str(task.get("target_language") or "ja"),
            image_mode=image_mode,
            before_image_upload_callback=enter_miaoshou_stage,
            progress_callback=lambda current, total: update_task_progress(
                task_id,
                "images",
                current,
                total,
                f"正在处理图片 {current}/{total}",
                35 + round((max(0, min(current, total)) / max(total, 1)) * 45),
            ),
            status_callback=lambda message, percent: update_task_progress(
                task_id,
                "images",
                1,
                1,
                message,
                percent,
            ),
        )
    except Exception as exc:
        release_miaoshou_stage()
        errors.append(f"自动上架处理异常：{exc}")
        return finish_failed_without_template(
            task,
            status="failed",
            message="自动上架处理异常，已停止流程。",
            steps=steps,
            errors=errors,
            product_infos=[product],
            progress_message="处理异常，流程已停止",
        )
    update_task_progress(task_id, "template", 0, 1, "正在生成妙手模板", 84)
    steps.append("已完成标题、SKU 和商品描述优化。")
    if optimized.get("image_notice"):
        steps.append(str(optimized["image_notice"]))
    image_result = optimized.get("image_result") if isinstance(optimized.get("image_result"), dict) else {}
    sku_required_value = optimized.get("sku_image_required")
    sku_target = int(sku_required_value) if sku_required_value is not None else len(optimized.get("optimized_skus") or [])
    sku_image_count = len(optimized.get("clean_sku_images") or [])
    main_image_count = len(optimized.get("clean_main_images") or [])
    detail_image_count = len(optimized.get("clean_detail_images") or [])
    image_ready = main_image_count > 0 and sku_image_count >= sku_target
    image_errors = [str(error) for error in (image_result.get("errors") or []) if str(error).strip()]
    image_ok = image_ready
    if not optimized.get("optimized_skus"):
        image_ok = False
        errors.append("SKU 图处理后没有可保留的 SKU，已停止自动导入；请人工复核 SKU 图片或降低 SKU 图要求。")
    if not image_ready:
        missing_parts: list[str] = []
        if main_image_count <= 0:
            missing_parts.append("主图为空")
        if sku_image_count < sku_target:
            missing_parts.append(f"SKU图未达标，当前 {sku_image_count}/{sku_target}")
        errors.append(
            f"图片数量不足：主图 {main_image_count}/{main_target}，"
            f"SKU图 {sku_image_count}/{sku_target}。详情图当前 {detail_image_count} 张，不做数量限制；主图不足 5 张允许继续上架。"
        )
        missing_sku_specs = [str(item) for item in (optimized.get("sku_image_missing_specs") or []) if str(item).strip()]
        if missing_sku_specs:
            errors.append(
                f"SKU 有源图但处理/上传后缺失，已按要求阻断自动导入。缺失规格：{'、'.join(missing_sku_specs[:30])}"
                + ("。" if len(missing_sku_specs) <= 30 else f" 等 {len(missing_sku_specs)} 个。")
            )
        errors.append(
            "失败定位："
            + "；".join(missing_parts)
            + "。仅工厂/供应链宣传图或纯文字图会删除；SKU 删光或主图为空才会阻断流程。"
        )
    errors.extend(image_errors)

    if not image_ok:
        steps.append("图片处理存在失败或数量不足：已停止自动导入，避免不完整商品进入公用采集箱。")
        release_miaoshou_stage()
        return finish_failed_without_template(
            task,
            status="image_failed",
            message="图片处理失败或数量不足，已停止自动上架流程。",
            steps=steps,
            errors=errors,
            product_infos=[optimized],
            progress_message="图片处理失败，流程已停止",
        )

    template_image_errors = validate_template_images_from_miaoshou_space(optimized)
    if template_image_errors:
        errors.extend(template_image_errors)
        errors.append("失败定位：导入妙手前二次检查失败，模板图片链接必须全部来自本次妙手图片空间上传结果；已停止流程，不生成妙手模板，也不会自动导入妙手。")
        release_miaoshou_stage()
        return finish_failed_without_template(
            task,
            status="image_failed",
            message="图片链接二次校验失败，已停止自动上架流程。",
            steps=steps,
            errors=errors,
            product_infos=[optimized],
            progress_message="图片链接校验失败，流程已停止",
        )

    try:
        output_path = build_miaoshou_import_xls(task["task_id"], optimized)
    except Exception as exc:
        release_miaoshou_stage()
        errors.append(f"生成妙手模板失败：{exc}")
        return finish_failed_without_template(
            task,
            status="template_failed",
            message="生成妙手模板失败，已停止自动上架流程。",
            steps=steps,
            errors=errors,
            product_infos=[optimized],
            progress_message="模板生成失败，流程已停止",
        )
    template_path_for_result = str(output_path)
    update_task_progress(task_id, "template", 1, 1, "妙手模板已生成", 88)
    steps.append(f"已按妙手导入模板生成文件：{output_path.name}")

    import_result: dict[str, Any] | None = None
    update_task_progress(task_id, "miaoshou", 0, 1, "正在导入妙手公用采集箱", 92)
    import_result = import_template_to_miaoshou(db, Path(output_path), str(task.get("erp_url") or ""), task_id=task_id)
    steps.extend(import_result.get("steps", []))
    errors.extend(import_result.get("errors", []))
    ok = bool(import_result.get("ok")) and not any("Oxylabs" in error for error in errors)
    status = "imported" if import_result.get("ok") else "import_failed"
    message = "已生成妙手模板并导入公用采集箱。" if import_result.get("ok") else "模板已生成，但自动导入妙手失败，请查看错误和截图。"
    if not import_result.get("ok"):
        steps.append("妙手导入失败，已按要求保留本次生成的模板文件，方便手动导入或复查。")
        errors.append("失败定位：妙手导入失败；模板文件已保留，请先修复妙手登录/导入入口识别问题后可手动导入或重新运行。")

    result = task | {
        "status": status,
        "ok": ok and not any("Oxylabs" in error for error in errors),
        "message": message if not errors else f"{message} 但存在需要复核的问题。",
        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "steps": steps,
        "errors": errors,
        "product_infos": [optimized],
        "template_path": template_path_for_result,
        "import_result": import_result,
        "progress": {
            "stage": "done",
            "current": 1,
            "total": 1,
            "message": message,
            "percent": 100,
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        },
    }
    _record_task(result)
    release_miaoshou_stage()
    return result


def error_is_blocking_for_product(error_text: str) -> bool:
    text = str(error_text or "").strip()
    if not text:
        return False
    blocking_tokens = (
        "图片数量不足",
        "主图第",
        "模板图片",
        "妙手图片空间上传失败",
        "不是本次妙手图片空间上传返回的链接",
        "no_images",
    )
    if any(token in text for token in blocking_tokens):
        return True
    detail_tokens = (
        "详情图",
        "已删除详情图",
        "已预筛删除不适合上架的详情图",
        "处理后的详情图",
    )
    if any(token in text for token in detail_tokens):
        return False
    if "SKU" in text or "SKU图" in text:
        return False
    if "AI MediaKit" in text and ("图片翻译" in text or "日语翻译" in text):
        return False
    return False


def run_1688_batch_publish_task(db: Session, task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    offer_urls = [str(url) for url in (task.get("offer_urls") or []) if str(url).strip()]
    image_mode = normalize_image_mode(task.get("image_mode"))
    mode_settings = image_mode_settings(image_mode)
    main_target = int(mode_settings["main_target"])
    steps: list[str] = []
    errors: list[str] = []
    products: list[dict[str, Any]] = []
    miaoshou_lock_acquired = False
    miaoshou_login_done = False
    miaoshou_stage_lock = Lock()

    def enter_miaoshou_stage() -> None:
        nonlocal miaoshou_lock_acquired, miaoshou_login_done
        with miaoshou_stage_lock:
            if not miaoshou_lock_acquired:
                update_task_progress(task_id, "miaoshou_wait", 0, 1, "等待妙手批量上传/导入队列", 78)
                MIAOSHOU_FLOW_LOCK.acquire()
                miaoshou_lock_acquired = True
            if not miaoshou_login_done:
                ensure_miaoshou_login_state(db, task_id, str(task.get("erp_url") or ""))
                miaoshou_login_done = True

    def release_miaoshou_stage() -> None:
        nonlocal miaoshou_lock_acquired
        with miaoshou_stage_lock:
            if miaoshou_lock_acquired:
                miaoshou_lock_acquired = False
                MIAOSHOU_FLOW_LOCK.release()

    def process_one(index: int, offer_url: str) -> dict[str, Any]:
        worker_db = SessionLocal()
        product_errors: list[str] = []
        try:
            update_task_progress(
                task_id,
                "fetch",
                index - 1,
                len(offer_urls),
                f"正在并发抓取第 {index}/{len(offer_urls)} 个商品",
                5 + round((index - 1) / max(len(offer_urls), 1) * 10),
            )
            raw_page = fetch_1688_page_with_oxylabs(worker_db, offer_url, task_id=task_id)
            product = extract_1688_product(offer_url, raw_page.get("html", ""), raw_page.get("raw", {}))
            parse_errors: list[str] = []
            if not clean_html_text(str(product.get("title") or "")):
                parse_errors.append("未能从 1688 页面解析到商品标题")
            main_source_count = len(unique_urls(product.get("main_images", []) or []))
            detail_source_count = len(unique_urls(product.get("detail_images", []) or []))
            sku_source_count = len(unique_urls([str(sku.get("image_url") or "") for sku in (product.get("skus") or []) if str(sku.get("image_url") or "").strip()]))
            if main_source_count + detail_source_count + sku_source_count < main_target:
                parse_errors.append(
                    f"可补主图的源图数量不足：主图 {main_source_count} 张，SKU图 {sku_source_count} 张，详情图 {detail_source_count} 张，合计不足 {main_target} 张"
                )
            valid_skus = [sku for sku in (product.get("skus") or []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
            if not valid_skus:
                parse_errors.append("未能从 1688 页面解析到有效 SKU")
            if parse_errors:
                raise AutoPublishError("；".join(parse_errors))

            update_task_progress(
                task_id,
                "copy",
                index,
                len(offer_urls),
                f"正在并发优化第 {index}/{len(offer_urls)} 个商品",
                18 + round(index / max(len(offer_urls), 1) * 12),
            )
            optimized = optimize_for_japan_listing(
                worker_db,
                product,
                f"{task_id}_{index:02d}",
                target_language=str(task.get("target_language") or "ja"),
                image_mode=image_mode,
                before_image_upload_callback=enter_miaoshou_stage,
                progress_callback=lambda current, total, item_index=index: update_task_progress(
                    task_id,
                    "images",
                    current,
                    total,
                    f"第 {item_index}/{len(offer_urls)} 个商品图片处理中 {current}/{total}",
                    30 + round((item_index / max(len(offer_urls), 1)) * 45),
                ),
                status_callback=lambda message, percent, item_index=index: update_task_progress(
                    task_id,
                    "images",
                    item_index,
                    len(offer_urls),
                    f"第 {item_index}/{len(offer_urls)} 个商品：{message}",
                    percent,
                ),
            )
            image_result = optimized.get("image_result") if isinstance(optimized.get("image_result"), dict) else {}
            sku_target = int(optimized.get("sku_image_required") or 0)
            sku_image_count = len(optimized.get("clean_sku_images") or [])
            main_image_count = len(optimized.get("clean_main_images") or [])
            if not optimized.get("optimized_skus"):
                product_errors.append("SKU 图处理后没有可保留的 SKU，已跳过该商品。")
            if main_image_count <= 0 or sku_image_count < sku_target:
                product_errors.append(f"图片数量不足：主图 {main_image_count}/{main_target}，SKU图 {sku_image_count}/{sku_target}。")
            for error in image_result.get("errors") or []:
                error_text = str(error).strip()
                if not error_text:
                    continue
                if error_is_blocking_for_product(error_text):
                    product_errors.append(error_text)
            product_errors.extend(validate_template_images_from_miaoshou_space(optimized))
            if product_errors:
                raise AutoPublishError("；".join(product_errors[:8]))
            return {"index": index, "offer_url": offer_url, "ok": True, "product": optimized}
        except Exception as exc:
            return {"index": index, "offer_url": offer_url, "ok": False, "error": str(exc)}
        finally:
            worker_db.close()

    try:
        oxylabs_pool_size = max(1, len(get_oxylabs_config_pool(db)))
        mediakit_pool_size = max(1, len(get_model_configs_for_translation()))
        worker_count = min(BATCH_PRODUCT_WORKERS, max(len(offer_urls), 1), max(1, oxylabs_pool_size * 2), max(1, mediakit_pool_size * 2))
        steps.append(
            f"已开启批量并发处理：{worker_count} 个商品线程同时抓取/优化/处理图片。"
            f"资源池：Oxylabs {oxylabs_pool_size} 组，AI MediaKit {mediakit_pool_size} 组；成功商品会合并为一个模板，失败商品只记录原因。"
        )
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(process_one, index, offer_url): (index, offer_url)
                for index, offer_url in enumerate(offer_urls, start=1)
            }
            for future in as_completed(future_map):
                index, offer_url = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"index": index, "offer_url": offer_url, "ok": False, "error": str(exc)}
                results.append(result)
                completed = len(results)
                update_task_progress(
                    task_id,
                    "images",
                    completed,
                    len(offer_urls),
                    f"批量商品已完成 {completed}/{len(offer_urls)} 个",
                    30 + round(completed / max(len(offer_urls), 1) * 50),
                )

        for result in sorted(results, key=lambda item: int(item.get("index") or 0)):
            index = int(result.get("index") or 0)
            offer_url = str(result.get("offer_url") or "")
            if result.get("ok"):
                optimized = result.get("product") if isinstance(result.get("product"), dict) else {}
                products.append(optimized)
                steps.append(f"第 {index} 个商品已处理完成：{optimized.get('title') or offer_url}")
            else:
                error = str(result.get("error") or "未知错误")
                errors.append(f"第 {index} 个商品处理失败：{offer_url}；原因：{error}")
                steps.append(f"第 {index} 个商品处理失败，已跳过：{offer_url}")

        if not products:
            release_miaoshou_stage()
            return finish_failed_without_template(
                task,
                status="batch_failed",
                message="批量商品全部处理失败，未生成妙手模板。",
                steps=steps,
                errors=errors,
                product_infos=[],
                progress_message="批量处理失败",
            )

        update_task_progress(task_id, "template", len(products), len(offer_urls), "正在生成批量妙手模板", 88)
        output_path = build_miaoshou_import_xls_multi(task_id, products)
        steps.append(f"已生成批量妙手导入模板：{output_path.name}，包含 {len(products)} 个商品。")
        update_task_progress(task_id, "miaoshou", 0, 1, "正在导入批量模板到妙手公用采集箱", 92)
        if not miaoshou_lock_acquired:
            enter_miaoshou_stage()
        import_result = import_template_to_miaoshou(db, output_path, str(task.get("erp_url") or ""), task_id=task_id)
        steps.extend(import_result.get("steps", []))
        errors.extend(import_result.get("errors", []))
        status = "imported" if import_result.get("ok") and not errors else ("batch_partial_failed" if products else "batch_failed")
        ok = bool(import_result.get("ok")) and not errors
        message = (
            f"批量模板已导入妙手：成功写入 {len(products)} 个商品。"
            if ok
            else f"批量模板已生成，成功处理 {len(products)}/{len(offer_urls)} 个商品，但存在失败或导入问题。"
        )
        if not import_result.get("ok"):
            steps.append("妙手导入失败，已按要求保留本次生成的批量模板文件，方便手动导入或复查。")
        result = task | {
            "status": status,
            "ok": ok,
            "message": message,
            "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "steps": steps,
            "errors": errors,
            "product_infos": products,
            "template_path": str(output_path),
            "import_result": import_result,
            "progress": {
                "stage": "done",
                "current": len(products),
                "total": len(offer_urls),
                "message": message,
                "percent": 100,
                "updated_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            },
        }
        _record_task(result)
        return result
    finally:
        release_miaoshou_stage()


class AutoPublishError(RuntimeError):
    pass


def dedupe_tuple_pool(items: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    result: list[tuple[Any, ...]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def pick_from_pool(pool_name: str, items: list[Any]) -> Any:
    if not items:
        raise AutoPublishError(f"{pool_name} 配置池为空。")
    with CONFIG_POOL_LOCK:
        index = CONFIG_POOL_INDEX.get(pool_name, 0)
        CONFIG_POOL_INDEX[pool_name] = index + 1
    return items[index % len(items)]


def retryable_external_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    return any(
        token in lowered
        for token in (
            "429",
            "too many requests",
            "rate limit",
            "timed out",
            "timeout",
            "ssleoferror",
            "connection reset",
            "connection aborted",
            "temporarily",
            "try again",
            "read timed out",
            "max retries exceeded",
        )
    )


def normalize_1688_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        url = f"https://{url}"
    if "1688.com" not in url:
        raise ValueError("当前只支持 1688 商品链接。")
    return url


def get_oxylabs_credentials(db: Session) -> tuple[str, str]:
    username, password, _endpoint = get_oxylabs_config(db)
    return username, password


def get_oxylabs_config(db: Session) -> tuple[str, str, str]:
    configs = get_oxylabs_config_pool(db)
    if not configs:
        raise AutoPublishError("Oxylabs 账号未配置：请在第三方 API 配置 oxylabs，或设置 OXYLABS_USERNAME/OXYLABS_PASSWORD。")
    username, password, endpoint = pick_from_pool("oxylabs", configs)
    return username, password, endpoint.rstrip("/")


def get_oxylabs_config_pool(db: Session) -> list[tuple[str, str, str]]:
    rows = db.scalars(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "oxylabs", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    ).all()
    configs: list[tuple[str, str, str]] = []
    for row in rows:
        username = str(row.access_key_encrypted or "").strip()
        password = str(row.secret_key_encrypted or "").strip()
        endpoint = str(row.api_base_url or DEFAULT_OXYLABS_REALTIME_URL).strip()
        if username and password:
            configs.append((username, password, endpoint.rstrip("/")))
    env_username = os.getenv("OXYLABS_USERNAME", "").strip()
    env_password = os.getenv("OXYLABS_PASSWORD", "").strip()
    if env_username and env_password:
        configs.append((env_username, env_password, os.getenv("OXYLABS_REALTIME_URL", DEFAULT_OXYLABS_REALTIME_URL).rstrip("/")))
    return dedupe_tuple_pool(configs)


def get_miaoshou_credentials(db: Session, task_id: str | None = None) -> tuple[str, str]:
    if task_id and task_id in MIAOSHOU_TASK_CREDENTIALS:
        return MIAOSHOU_TASK_CREDENTIALS[task_id]
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "miaoshou", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    username = os.getenv("MIAOSHOU_USERNAME", "")
    password = os.getenv("MIAOSHOU_PASSWORD", "")
    if config:
        username = config.access_key_encrypted or username
        password = config.secret_key_encrypted or password
    if not username or not password:
        raise AutoPublishError("妙手账号未配置：请在第三方 API 配置 miaoshou，或设置 MIAOSHOU_USERNAME/MIAOSHOU_PASSWORD。")
    return username, password


def get_miaoshou_credentials_optional(db: Session, task_id: str | None = None) -> tuple[str, str] | None:
    try:
        return get_miaoshou_credentials(db, task_id)
    except AutoPublishError:
        return None


def should_run_miaoshou_headless() -> bool:
    configured = os.getenv("MIAOSHOU_HEADLESS")
    if configured is not None:
        return configured.strip().lower() not in {"0", "false", "no", "off"}
    if os.name != "nt" and not os.getenv("DISPLAY"):
        return True
    return False


def ensure_miaoshou_login_state(db: Session, task_id: str, erp_url: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AutoPublishError(f"Playwright 未安装，无法登录妙手上传图片：{exc}") from exc

    headless = should_run_miaoshou_headless()
    target_url = erp_url or "https://erp.91miaoshou.com/?ac=1og270"
    username, password = get_miaoshou_credentials(db, task_id)
    storage_path = miaoshou_storage_state_path_for_username(username)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(**browser_launch_options(headless))
        except Exception as exc:  # noqa: BLE001
            raise AutoPublishError(f"妙手浏览器启动失败：{exc}") from exc
        context_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            close_miaoshou_popups(page)
            login_miaoshou(page, username, password, force=True)
            page.wait_for_timeout(1200)
            close_miaoshou_popups(page)
            context.storage_state(path=str(storage_path))
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


def save_miaoshou_credentials_from_payload(db: Session, payload: dict[str, Any]) -> bool:
    username = str(payload.get("miaoshou_username") or "").strip()
    password = str(payload.get("miaoshou_password") or "").strip()
    if not username and not password:
        return False
    if not username or not password:
        raise ValueError("妙手账号和密码需要同时填写。")

    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "miaoshou")
        .order_by(ThirdPartyConfig.id.desc())
    )
    if not config:
        config = ThirdPartyConfig(
            config_name="妙手ERP账号",
            service_type="miaoshou",
            api_base_url=str(payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270"),
            status=1,
        )
    config.config_name = config.config_name or "妙手ERP账号"
    config.service_type = "miaoshou"
    config.api_base_url = str(payload.get("erp_url") or config.api_base_url or "https://erp.91miaoshou.com/?ac=1og270")
    config.access_key_encrypted = username
    config.secret_key_encrypted = password
    config.status = 1
    config.remark = "auto_publish:miaoshou_login"
    db.add(config)
    db.commit()
    return True


def post_oxylabs_with_powershell(endpoint: str, username: str, password: str, payload: dict[str, Any], original_error: str) -> dict[str, Any]:
    _ensure_runtime_dir()
    temp_prefix = RUNTIME_DIR / f"oxylabs_request_{uuid4().hex}"
    payload_path = temp_prefix.with_suffix(".json")
    response_path = temp_prefix.with_suffix(".response.json")
    error_path = temp_prefix.with_suffix(".error.txt")
    script_path = temp_prefix.with_suffix(".ps1")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    script_path.write_text(
        r'''
$ErrorActionPreference = "Stop"
$endpoint = $args[0]
$username = $args[1]
$password = $args[2]
$payloadPath = $args[3]
$responsePath = $args[4]
$errorPath = $args[5]
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
} catch {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
$pair = "${username}:${password}"
$bytes = [System.Text.Encoding]::ASCII.GetBytes($pair)
$auth = [Convert]::ToBase64String($bytes)
$headers = @{ Authorization = "Basic $auth"; "Content-Type" = "application/json"; "Accept" = "application/json" }
$body = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8
try {
  $result = Invoke-RestMethod -Uri $endpoint -Method Post -Headers $headers -Body $body -ContentType "application/json" -TimeoutSec 120
  $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $responsePath -Encoding UTF8
} catch {
  $message = $_.Exception.Message
  if ($_.Exception.Response) {
    $message = "HTTP " + [int]$_.Exception.Response.StatusCode + " " + $message
  }
  Set-Content -LiteralPath $errorPath -Value $message -Encoding UTF8
  exit 1
}
'''.strip(),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                endpoint,
                username,
                password,
                str(payload_path),
                str(response_path),
                str(error_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=140,
        )
        return json.loads(response_path.read_text(encoding="utf-8-sig"))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        detail = error_path.read_text(encoding="utf-8", errors="ignore") if error_path.exists() else ""
        raise AutoPublishError(f"Oxylabs 请求失败：Python TLS 失败：{original_error}；系统网络兜底也失败：{detail or exc}") from exc
    finally:
        for path in (payload_path, response_path, error_path, script_path):
            try:
                path.unlink()
            except OSError:
                pass


def post_aimediakit_with_powershell(endpoint: str, api_key: str, payload: dict[str, Any], original_error: str) -> dict[str, Any]:
    _ensure_runtime_dir()
    temp_prefix = RUNTIME_DIR / f"aimediakit_request_{uuid4().hex}"
    payload_path = temp_prefix.with_suffix(".json")
    response_path = temp_prefix.with_suffix(".response.json")
    error_path = temp_prefix.with_suffix(".error.txt")
    script_path = temp_prefix.with_suffix(".ps1")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    script_path.write_text(
        r'''
$ErrorActionPreference = "Stop"
$endpoint = $args[0]
$apiKey = $args[1]
$payloadPath = $args[2]
$responsePath = $args[3]
$errorPath = $args[4]
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
} catch {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
$headers = @{ Authorization = "Bearer $apiKey"; "Content-Type" = "application/json"; "Accept" = "application/json" }
$body = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8
try {
  $result = Invoke-RestMethod -Uri $endpoint -Method Post -Headers $headers -Body $body -ContentType "application/json" -TimeoutSec 180
  $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $responsePath -Encoding UTF8
} catch {
  $message = $_.Exception.Message
  if ($_.Exception.Response) {
    $message = "HTTP " + [int]$_.Exception.Response.StatusCode + " " + $message
  }
  Set-Content -LiteralPath $errorPath -Value $message -Encoding UTF8
  exit 1
}
'''.strip(),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                endpoint,
                api_key,
                str(payload_path),
                str(response_path),
                str(error_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=200,
        )
        return json.loads(response_path.read_text(encoding="utf-8-sig"))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        detail = error_path.read_text(encoding="utf-8", errors="ignore") if error_path.exists() else ""
        raise requests.RequestException(f"Python TLS 失败：{original_error}；系统网络兜底也失败：{detail or exc}") from exc
    finally:
        for path in (payload_path, response_path, error_path, script_path):
            try:
                path.unlink()
            except OSError:
                pass


def download_remote_image_with_powershell(image_url: str, original_error: str) -> bytes:
    _ensure_runtime_dir()
    temp_prefix = RUNTIME_DIR / f"remote_image_{uuid4().hex}"
    output_path = temp_prefix.with_suffix(".img")
    error_path = temp_prefix.with_suffix(".error.txt")
    script_path = temp_prefix.with_suffix(".ps1")
    script_path.write_text(
        r'''
$ErrorActionPreference = "Stop"
$url = $args[0]
$outputPath = $args[1]
$errorPath = $args[2]
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
} catch {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
try {
  Invoke-WebRequest -Uri $url -OutFile $outputPath -TimeoutSec 120 -Headers @{ "User-Agent" = "Mozilla/5.0 TKAutoPublish/1.0" }
} catch {
  Set-Content -LiteralPath $errorPath -Value $_.Exception.Message -Encoding UTF8
  exit 1
}
'''.strip(),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), image_url, str(output_path), str(error_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=140,
        )
        data = output_path.read_bytes()
        if not data:
            raise requests.RequestException("系统网络兜底下载返回空内容")
        return data
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, requests.RequestException) as exc:
        detail = error_path.read_text(encoding="utf-8", errors="ignore") if error_path.exists() else ""
        raise requests.RequestException(f"Python TLS 下载失败：{original_error}；系统网络兜底下载也失败：{detail or exc}") from exc
    finally:
        for path in (output_path, error_path, script_path):
            try:
                path.unlink()
            except OSError:
                pass


def import_template_to_miaoshou(
    db: Session,
    template_path: Path,
    erp_url: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    steps: list[str] = []
    errors: list[str] = []
    screenshots: list[str] = []

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"ok": False, "steps": [], "errors": [f"Playwright 未安装：{exc}"], "screenshots": []}

    headless = should_run_miaoshou_headless()
    target_url = erp_url or "https://erp.91miaoshou.com/?ac=1og270"
    try:
        username, password = get_miaoshou_credentials(db, task_id)
    except AutoPublishError as exc:
        return {"ok": False, "steps": steps, "errors": [str(exc)], "screenshots": []}
    storage_path = miaoshou_storage_state_path_for_username(username)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(**browser_launch_options(headless))
        except Exception as exc:  # noqa: BLE001 - surface browser setup as a normal import failure.
            return {"ok": False, "steps": steps, "errors": [f"妙手浏览器启动失败：{exc}"], "screenshots": []}
        context_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
        using_saved_state = storage_path.exists()
        if using_saved_state:
            context_kwargs["storage_state"] = str(storage_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            steps.append(f"已打开妙手 ERP：{target_url}")
            close_miaoshou_popups(page)
            if using_saved_state:
                steps.append("已使用本次保存的妙手登录态进入导入流程。")
                if not is_miaoshou_logged_in(page):
                    steps.append("保存的妙手登录态已失效，正在重新填写账号密码登录。")
                    login_miaoshou(page, username, password, force=True)
                    page.wait_for_timeout(2000)
                    close_miaoshou_popups(page)
                    context.storage_state(path=str(storage_path))
                    steps.append("已重新登录并更新妙手登录态。")
            else:
                login_miaoshou(page, username, password, force=True)
                steps.append("已填写妙手账号密码；如页面出现验证码，请在妙手窗口手动完成验证。")
                page.wait_for_timeout(2000)
                close_miaoshou_popups(page)
                context.storage_state(path=str(storage_path))
                steps.append("已保存妙手登录态。")
            open_miaoshou_public_collection(page)
            steps.append("已进入公用采集箱/导入入口。")
            upload_miaoshou_template(page, template_path)
            steps.append("已上传妙手产品导入模板。")
            submit_miaoshou_import(page)
            context.storage_state(path=str(storage_path))
            steps.append("已提交导入任务，请在妙手后台确认导入结果。")
            return {"ok": True, "steps": steps, "errors": [], "screenshots": []}
        except Exception as exc:  # noqa: BLE001 - automation must preserve page evidence.
            screenshot = RUNTIME_DIR / f"miaoshou_import_failed_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
            try:
                page.screenshot(path=str(screenshot), full_page=True)
                screenshots.append(str(screenshot))
            except Exception:
                pass
            if isinstance(exc, PlaywrightTimeoutError):
                errors.append(f"妙手页面等待超时：{exc}")
            else:
                errors.append(f"妙手自动导入失败：{exc}")
            return {"ok": False, "steps": steps, "errors": errors, "screenshots": screenshots}
        finally:
            keep_open = os.getenv("MIAOSHOU_KEEP_BROWSER_ON_ERROR", "1") == "1" and errors
            if not keep_open:
                browser.close()


def browser_launch_options(headless: bool) -> dict[str, Any]:
    options: dict[str, Any] = {"headless": headless, "slow_mo": 80 if not headless else 0}
    for browser_path in LOCAL_BROWSER_PATHS:
        if browser_path.exists():
            options["executable_path"] = str(browser_path)
            break
    return options


def close_miaoshou_popups(page: Any) -> None:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    for _ in range(6):
        clicked = False
        for text in ("我知道了", "知道了", "跳过", "关闭", "稍后再说", "取消", "暂不处理", "下次再说", "暂不开启", "我再想想"):
            if click_text_if_visible(page, text, exact=False, timeout=800):
                clicked = True
        for selector in (
            ".el-dialog__headerbtn",
            ".el-dialog__close",
            ".el-message-box__headerbtn",
            ".el-message-box__close",
            ".ant-modal-close",
            ".ant-drawer-close",
            ".ivu-modal-close",
            ".layui-layer-close",
            ".layui-layer-setwin a",
            ".modal-close",
            ".close",
            ".close-btn",
            ".popup-close",
            ".dialog-close",
            "[aria-label='Close']",
            "[aria-label='close']",
            "[title='关闭']",
            "button:has-text('×')",
            "span:has-text('×')",
            "i.el-icon-close",
        ):
            try:
                locator = page.locator(selector)
                for index in range(min(locator.count(), 5)):
                    item = locator.nth(index)
                    if item.is_visible(timeout=300):
                        item.click(timeout=1000)
                        clicked = True
                        break
            except Exception:
                pass
        if not clicked:
            break
        page.wait_for_timeout(600)


def login_miaoshou(page: Any, username: str, password: str, force: bool = False) -> None:
    if not force and is_miaoshou_logged_in(page):
        close_miaoshou_popups(page)
        return
    fill_miaoshou_login_account(page, username)
    fill_first_visible(page, ["input[type='password']", "input[placeholder*='密码']"], password)
    if has_visible_captcha_input(page):
        page.bring_to_front()
        wait_for_miaoshou_manual_login(page)
        close_miaoshou_popups(page)
        return
    click_first_visible(page, ["button:has-text('立即登录')", "button:has-text('登录')", "text=立即登录", "text=登录", "button[type='submit']"], timeout=5000)
    wait_for_miaoshou_manual_login(page)
    close_miaoshou_popups(page)


def fill_miaoshou_login_account(page: Any, username: str) -> None:
    selectors = [
        "input[name='username']",
        "input[name='account']",
        "input[placeholder*='手机号']",
        "input[placeholder*='手机']",
        "input[placeholder*='子账号']",
        "input[placeholder*='邮箱']",
        "input[placeholder*='账号']",
        "input[placeholder*='用户名']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    item.fill(username)
                    return
            except Exception:
                pass
    filled = page.evaluate(
        """
        (value) => {
          const inputs = Array.from(document.querySelectorAll("input"));
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
          };
          const isCaptcha = (el) => /验证码|校验码|captcha/i.test(el.placeholder || "") || el.getBoundingClientRect().top > 390;
          const isPassword = (el) => el.type === "password" || /密码/i.test(el.placeholder || "");
          let target = inputs.find((el) => visible(el) && !isCaptcha(el) && !isPassword(el) && /手机|账号|邮箱|用户名|子账号/i.test(el.placeholder || ""));
          if (!target) {
            const passwordInput = inputs.find((el) => visible(el) && isPassword(el));
            if (passwordInput) {
              const passwordTop = passwordInput.getBoundingClientRect().top;
              target = inputs
                .filter((el) => visible(el) && !isCaptcha(el) && !isPassword(el) && el.getBoundingClientRect().top < passwordTop)
                .pop();
            }
          }
          if (!target) return false;
          target.focus();
          target.value = value;
          target.dispatchEvent(new Event("input", { bubbles: true }));
          target.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        }
        """,
        username,
    )
    if not filled:
        raise AutoPublishError("没有找到妙手账号输入框。")


def has_visible_captcha_input(page: Any) -> bool:
    for selector in ("input[placeholder*='验证码']", "input[placeholder*='校验码']", "input[placeholder*='输入验证码']"):
        locator = page.locator(selector)
        for index in range(locator.count()):
            try:
                if locator.nth(index).is_visible(timeout=500):
                    return True
            except Exception:
                pass
    return False


def wait_for_miaoshou_manual_login(page: Any) -> None:
    deadline_ms = 600_000
    page.wait_for_function(
        """() => {
            const text = document.body ? document.body.innerText : "";
            const hasCaptcha = !!document.querySelector("input[placeholder*='验证码'], input[placeholder*='校验码']");
            const hasLoginButton = /立即登录|登录/.test(text) && hasCaptcha;
            const inBackend = /产品\\s+订单\\s+托管|公用采集箱|货盘中心|快速上货|同步/.test(text);
            return !hasCaptcha && !hasLoginButton && inBackend;
        }""",
        timeout=deadline_ms,
    )


def is_miaoshou_logged_in(page: Any) -> bool:
    try:
        if has_visible_captcha_input(page):
            return False
        text = page.locator("body").inner_text(timeout=2000)
        return bool(re.search(r"产品\s+订单\s+托管|公用采集箱|货盘中心|快速上货|同步", text))
    except Exception:
        return False


def open_miaoshou_public_collection(page: Any) -> None:
    close_miaoshou_popups(page)
    if is_miaoshou_public_collection_page(page):
        return
    for _ in range(4):
        close_miaoshou_popups(page)
        if click_visible_text_by_script(page, "公用采集箱", exact=True, max_left=360):
            page.wait_for_timeout(2500)
            close_miaoshou_popups(page)
            if is_miaoshou_public_collection_page(page):
                return
        if click_text_if_visible(page, "公用采集箱", exact=False, timeout=1500):
            page.wait_for_timeout(2500)
            close_miaoshou_popups(page)
            if is_miaoshou_public_collection_page(page):
                return
        if click_text_if_visible(page, "产品", exact=True, timeout=3000):
            page.wait_for_timeout(1000)
            close_miaoshou_popups(page)
        for text in ("公用采集箱", "采集箱"):
            if click_text_if_visible(page, text, exact=False, timeout=3000):
                page.wait_for_timeout(2500)
                close_miaoshou_popups(page)
                if is_miaoshou_public_collection_page(page):
                    return
    raise AutoPublishError("没有找到妙手公用采集箱或产品导入入口。")


def is_miaoshou_public_collection_page(page: Any) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2000)
        return "公用采集箱" in text and "导入产品" in text
    except Exception:
        return False


def upload_miaoshou_template(page: Any, template_path: Path) -> None:
    if not template_path.exists():
        raise AutoPublishError(f"模板文件不存在：{template_path}")
    close_miaoshou_popups(page)
    if click_text_if_visible(page, "导入产品", exact=False, timeout=5000):
        page.wait_for_timeout(800)
    if click_miaoshou_import_dropdown_item(page):
        page.wait_for_timeout(1200)
    else:
        for text in ("导入商品", "导入产品"):
            if click_text_if_visible(page, text, exact=True, timeout=3000):
                page.wait_for_timeout(1200)
                break
    file_inputs = page.locator("input[type='file']")
    if file_inputs.count():
        file_inputs.first.set_input_files(str(template_path), timeout=10000)
        page.wait_for_timeout(2500)
        return
    for text in ("点击或拖拽文件导入", "上传文件", "选择文件", "导入文件", "上传"):
        try:
            with page.expect_file_chooser(timeout=5000) as chooser_info:
                page.get_by_text(text, exact=False).first.click(timeout=3000)
            chooser_info.value.set_files(str(template_path))
            page.wait_for_timeout(2500)
            return
        except Exception:
            pass
    raise AutoPublishError("没有找到妙手模板上传控件。")


def click_miaoshou_import_dropdown_item(page: Any) -> bool:
    for selector in (
        ".el-dropdown-menu__item",
        ".ant-dropdown-menu-item",
        "[role='menuitem']",
        ".dropdown-menu li",
        ".el-popper li",
        ".popper li",
    ):
        try:
            locator = page.locator(selector)
            for index in range(locator.count()):
                item = locator.nth(index)
                if not item.is_visible(timeout=500):
                    continue
                text = re.sub(r"\s+", "", item.inner_text(timeout=1000))
                if text not in {"导入产品", "导入商品"}:
                    continue
                box = item.bounding_box(timeout=1000)
                if not box:
                    continue
                if box["x"] < 900 or box["y"] < 250:
                    continue
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                return True
        except Exception:
            pass
    try:
        return bool(
            page.evaluate(
                """() => {
                    const normalize = (value) => (value || "").replace(/\\s+/g, "").trim();
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style && style.visibility !== "hidden" && style.display !== "none"
                            && rect.width > 1 && rect.height > 1
                            && rect.bottom >= 0 && rect.right >= 0
                            && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
                    };
                    const wanted = new Set(["导入产品", "导入商品"]);
                    const importButtons = Array.from(document.querySelectorAll("button, a, div, span"))
                        .filter((el) => isVisible(el) && normalize(el.innerText || el.textContent || "") === "导入产品")
                        .map((el) => el.getBoundingClientRect())
                        .filter((rect) => rect.left > window.innerWidth * 0.55)
                        .sort((a, b) => a.top - b.top);
                    const buttonBottom = importButtons.length ? importButtons[0].bottom : 250;
                    const candidates = Array.from(document.querySelectorAll(
                        ".el-dropdown-menu__item, .ant-dropdown-menu-item, [role='menuitem'], .dropdown-menu li, .el-popper li, .popper li"
                    )).filter((el) => {
                        if (!isVisible(el)) return false;
                        const rect = el.getBoundingClientRect();
                        const text = normalize(el.innerText || el.textContent || "");
                        return wanted.has(text)
                            && rect.left > window.innerWidth * 0.55
                            && rect.top > buttonBottom
                            && rect.width < 260
                            && rect.height < 80;
                    }).sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return ar.top - br.top || br.left - ar.left;
                    });
                    if (!candidates.length) return false;
                    const el = candidates[0];
                    el.scrollIntoView({ block: "center", inline: "center" });
                    el.click();
                    return true;
                }"""
            )
        )
    except Exception:
        return False


def submit_miaoshou_import(page: Any) -> None:
    for text in ("确定", "确认导入", "开始导入", "提交", "导入"):
        try:
            locator = page.get_by_text(text, exact=False)
            if locator.count():
                locator.last.click(timeout=5000)
                page.wait_for_timeout(3500)
                return
        except Exception:
            pass
    raise AutoPublishError("模板已选择，但没有找到提交导入按钮。")


def fill_first_visible(page: Any, selectors: list[str], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=1000):
                    item.fill(value, timeout=3000)
                    return
            except Exception:
                pass
    raise AutoPublishError(f"没有找到可填写控件：{selectors[0]}")


def click_first_visible(page: Any, selectors: list[str], timeout: int = 3000) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=1000):
                    item.click(timeout=timeout)
                    return
            except Exception:
                pass
    raise AutoPublishError(f"没有找到可点击控件：{selectors[0]}")


def click_text_if_visible(page: Any, text: str, exact: bool = False, timeout: int = 3000) -> bool:
    try:
        locator = page.get_by_text(text, exact=exact)
        count = locator.count()
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=500):
                    item.click(timeout=timeout)
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def click_visible_text_by_script(page: Any, text: str, exact: bool = False, max_left: int | None = None) -> bool:
    try:
        return bool(
            page.evaluate(
                """({ text, exact, maxLeft }) => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style && style.visibility !== "hidden" && style.display !== "none"
                            && rect.width > 1 && rect.height > 1
                            && rect.bottom >= 0 && rect.right >= 0
                            && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
                    };
                    const normalize = (value) => (value || "").replace(/\\s+/g, "").trim();
                    const targetText = normalize(text);
                    const candidates = Array.from(document.querySelectorAll("a,button,span,div,li"))
                        .filter((el) => {
                            if (!isVisible(el)) return false;
                            const rect = el.getBoundingClientRect();
                            if (maxLeft !== null && rect.left > maxLeft) return false;
                            const ownText = normalize(el.innerText || el.textContent || "");
                            return exact ? ownText === targetText : ownText.includes(targetText);
                        })
                        .sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            return ar.left - br.left || ar.top - br.top;
                        });
                    if (!candidates.length) return false;
                    const el = candidates[0];
                    const clickable = el.closest("a,button,li,[role='menuitem'],.el-menu-item,.menu-item") || el;
                    clickable.scrollIntoView({ block: "center", inline: "center" });
                    clickable.click();
                    return true;
                }""",
                {"text": text, "exact": exact, "maxLeft": max_left},
            )
        )
    except Exception:
        return False


def fetch_1688_page_with_oxylabs(db: Session, offer_url: str, task_id: str = "") -> dict[str, Any]:
    configs = get_oxylabs_config_pool(db)
    if not configs:
        raise AutoPublishError("Oxylabs credentials not configured: add enabled third-party configs with service_type=oxylabs or set OXYLABS_USERNAME/OXYLABS_PASSWORD.")
    payload = {
        "source": "universal",
        "url": offer_url,
        "geo_location": "China",
        "render": "html",
        "parse": False,
    }
    errors: list[str] = []
    first_config = pick_from_pool("oxylabs", configs)
    ordered_configs = [first_config] + [item for item in configs if item != first_config]
    data: dict[str, Any] | None = None
    for config_index, (username, password, endpoint) in enumerate(ordered_configs, start=1):
        status_code: int | None = None
        usage_meta = {
            "pool_index": config_index,
            "pool_size": len(configs),
            "key_label": usage_key_label(f"oxylabs-{config_index}", username),
        }
        try:
            response = requests.post(endpoint, auth=(username, password), json=payload, timeout=90)
            status_code = response.status_code
            if response.status_code >= 400:
                error_text = f"HTTP {response.status_code} {response.text[:300]}"
                record_api_usage(
                    task_id,
                    provider="oxylabs",
                    purpose="fetch_1688_page",
                    model="universal_html_render",
                    endpoint=endpoint,
                    success=False,
                    status_code=status_code,
                    error=error_text,
                    meta=usage_meta,
                )
                errors.append(f"??{config_index}/{len(configs)} {error_text}")
                if retryable_external_error(error_text) and config_index < len(ordered_configs):
                    time.sleep(0.8 * config_index)
                    continue
                raise AutoPublishError("Oxylabs request failed: " + " | ".join(errors[-3:]))
            data = response.json()
            record_api_usage(
                task_id,
                provider="oxylabs",
                purpose="fetch_1688_page",
                model="universal_html_render",
                endpoint=endpoint,
                success=True,
                status_code=status_code,
                meta=usage_meta,
            )
            break
        except requests.RequestException as exc:
            try:
                data = post_oxylabs_with_powershell(endpoint, username, password, payload, str(exc))
                record_api_usage(
                    task_id,
                    provider="oxylabs",
                    purpose="fetch_1688_page",
                    model="universal_html_render",
                    endpoint=endpoint,
                    success=True,
                    request_count=2,
                    status_code=status_code,
                    meta={**usage_meta, "fallback": "powershell"},
                )
                break
            except Exception as fallback_exc:
                error_text = sanitize_secret_error(str(fallback_exc))
                errors.append(f"??{config_index}/{len(configs)} {error_text}")
                record_api_usage(
                    task_id,
                    provider="oxylabs",
                    purpose="fetch_1688_page",
                    model="universal_html_render",
                    endpoint=endpoint,
                    success=False,
                    request_count=2,
                    status_code=status_code,
                    error=error_text,
                    meta={**usage_meta, "fallback": "powershell"},
                )
                if retryable_external_error(error_text) and config_index < len(ordered_configs):
                    time.sleep(0.8 * config_index)
                    continue
                raise AutoPublishError("Oxylabs request failed: " + " | ".join(errors[-3:])) from fallback_exc
    if not data:
        raise AutoPublishError("Oxylabs request failed: " + " | ".join(errors[-3:]))
    result = (data.get("results") or [{}])[0] if isinstance(data, dict) else {}
    content = result.get("content") or data.get("content") if isinstance(data, dict) else ""
    if isinstance(content, dict):
        html = json.dumps(content, ensure_ascii=False)
    else:
        html = str(content or "")
    return {"html": html, "raw": data}


def extract_1688_product(offer_url: str, html: str, raw: dict[str, Any]) -> dict[str, Any]:
    offer_id_match = re.search(r"/offer/(\d+)", offer_url)
    offer_id = offer_id_match.group(1) if offer_id_match else ""
    title = first_match(
        html,
        [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            r'<title[^>]*>(.*?)</title>',
            r'"subject"\s*:\s*"([^"]+)"',
            r'"title"\s*:\s*"([^"]+)"',
        ],
    )
    title = clean_1688_title(title)
    image_source = normalize_image_source(html)
    image_urls = filter_product_image_urls(
        unique_urls(re.findall(r"https?://[^\"'<>\\\s]+(?:alicdn|1688)[^\"'<>\\\s]+\.(?:jpg|jpeg|png|webp)", image_source))
    )
    main_images, detail_images = split_1688_image_groups(image_urls)
    context_main_images = extract_context_main_images(html)
    if context_main_images:
        main_images = context_main_images
    context_detail_images = fetch_context_detail_images(html)
    if context_detail_images:
        detail_images = context_detail_images
    price = first_match(html, [r'"price"\s*:\s*"?(?P<value>\d+(?:\.\d+)?)', r"¥\s*(\d+(?:\.\d+)?)"])
    category = first_match(
        html,
        [
            r'"leafCategoryName"\s*:\s*"([^"]+)"',
            r'"categoryName"\s*:\s*"([^"]+)"',
            r'"catName"\s*:\s*"([^"]+)"',
        ],
    )
    props = parse_property_pairs(html)
    shipping_fee = parse_shipping_fee(html)
    sku_rows = parse_sku_rows(html, image_urls, price)
    if not sku_rows:
        sku_rows = [{"spec1": "默认", "spec2": "", "price": price or "0", "stock": 100, "image_url": image_urls[0] if image_urls else ""}]
    sku_image_urls = {normalize_image_url(str(row.get("image_url") or "")) for row in sku_rows if row.get("image_url")}
    detail_images = [url for url in detail_images if normalize_image_url(url) not in sku_image_urls][:DETAIL_IMAGE_LIMIT]
    if not detail_images:
        detail_images = [
            url for url in image_urls if normalize_image_url(url) not in set(main_images) | sku_image_urls
        ][:DETAIL_IMAGE_LIMIT]
    return {
        "offer_url": offer_url,
        "offer_id": offer_id,
        "title": title,
        "currency": "CNY",
        "price": price or "0",
        "shipping_fee": shipping_fee,
        "category": category,
        "main_images": main_images,
        "detail_images": detail_images[:DETAIL_IMAGE_LIMIT],
        "properties": props,
        "skus": sku_rows[:80],
        "raw_sample": {"html_length": len(html), "raw_keys": list(raw.keys())[:20] if isinstance(raw, dict) else []},
    }


def first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        value = match.groupdict().get("value") if match.groupdict() else match.group(1)
        if value:
            return value
    return ""


def clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = value.replace("\\u002F", "/")
    if "\\u" in value or "\\x" in value:
        try:
            value = bytes(value, "utf-8").decode("unicode_escape")
        except UnicodeError:
            pass
    value = repair_mojibake(value)
    return re.sub(r"\s+", " ", value).strip()


def clean_1688_title(value: str) -> str:
    title = clean_html_text(value)
    title = re.sub(r"\s*[-_—|｜]\s*(?:阿里巴巴|1688)\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*(?:-|\|)?\s*阿里巴巴\s*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def repair_mojibake(value: str) -> str:
    if not value or not re.search(r"[ÃÂæèéå]", value):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value
    if count_cjk(repaired) > count_cjk(value):
        return repaired
    return value


def count_cjk(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", value or ""))


def unique_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        item = normalize_full_image_url(url)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_image_url(url: str) -> str:
    item = str(url or "").replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&").strip()
    item = item.split("?")[0]
    if item.startswith("//"):
        item = f"https:{item}"
    return item


def normalize_full_image_url(url: str) -> str:
    item = normalize_image_url(url)
    item = re.sub(r"\.jpg_\.webp$", ".jpg", item, flags=re.IGNORECASE)
    item = re.sub(r"_b\.jpg$", ".jpg", item, flags=re.IGNORECASE)
    item = re.sub(r"\.(?:search|summ|220x220|310x310)\.jpg$", ".jpg", item, flags=re.IGNORECASE)
    return item


def normalize_image_source(html: str) -> str:
    return (
        html.replace("\\u002F", "/")
        .replace("\\/", "/")
        .replace("&amp;", "&")
        .replace("_!!", "_!!")
    )


def split_1688_image_groups(image_urls: list[str]) -> tuple[list[str], list[str]]:
    product_urls = [
        url
        for url in image_urls
        if not any(token in url.lower() for token in ("-0-rate", "tbvideo", "/rate/", "video", "avatar", "comment"))
    ]
    main_candidates: list[str] = []
    for url in product_urls:
        lower = url.lower()
        if any(token in lower for token in ("-0-cib", "/ibank/", "/cbu")):
            main_candidates.append(url)
    if not main_candidates:
        main_candidates = product_urls[:8]
    main_images = unique_urls(main_candidates)[:8]
    detail_candidates = [url for url in product_urls if url not in main_images]
    if not detail_candidates:
        detail_candidates = product_urls[8:28]
    if not detail_candidates:
        detail_candidates = main_images[:]
    return main_images, unique_urls(detail_candidates)[:DETAIL_IMAGE_LIMIT]


def extract_context_main_images(html: str) -> list[str]:
    for key in ("mainImageList", "imageList"):
        for match in re.finditer(r'"' + re.escape(key) + r'"\s*:\s*\[', html):
            array_text = extract_json_array_from(html, match.end() - 1)
            if not array_text:
                continue
            try:
                items = json.loads(array_text)
            except json.JSONDecodeError:
                continue
            urls: list[str] = []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    url = item.get("fullPathImageURI") or item.get("imageURI") or item.get("url")
                    if url:
                        urls.append(str(url))
            urls = filter_product_image_urls(unique_urls(urls))
            if urls:
                return urls[:8]
    return []


def fetch_context_detail_images(html: str) -> list[str]:
    detail_url = extract_detail_url(html)
    if not detail_url:
        return []
    try:
        response = requests.get(detail_url, headers={"User-Agent": "Mozilla/5.0 TKAutoPublish/1.0"}, timeout=25)
        response.raise_for_status()
    except requests.RequestException:
        return []
    urls = re.findall(
        r"https?://[^\"'<>\\\s]+(?:alicdn|1688|taobaocdn|tmall)[^\"'<>\\\s]+\.(?:jpg|jpeg|png|webp)",
        response.text,
    )
    return filter_product_image_urls(unique_urls(urls))[:30]


def extract_detail_url(html: str) -> str:
    match = re.search(r'"detailUrl"\s*:\s*"([^"]+)"', html)
    if not match:
        return ""
    return normalize_image_url(html_lib.unescape(match.group(1)))


def extract_json_array_from(text: str, start: int) -> str:
    if start < 0 or start >= len(text) or text[start] != "[":
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def filter_product_image_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    for url in urls:
        lower = url.lower()
        if any(
            token in lower
            for token in (
                "img.alicdn.com/tfs/",
                "gw.alicdn.com/tfs/",
                "icon",
                "logo",
                "sprite",
                "-tps-",
                "overseas_pic",
                "-0-rate",
                "tbvideo",
                "/rate/",
                "avatar",
            )
        ):
            continue
        size_match = re.search(r"[-_](\d{2,4})[-x_](\d{2,4})(?:\\.|$)", lower)
        if size_match:
            width, height = int(size_match.group(1)), int(size_match.group(2))
            if width < 240 or height < 240:
                continue
        if "alicdn.com" in lower and not any(token in lower for token in ("cbu", "ibank", "bao/uploaded", "imgextra")):
            continue
        result.append(url)
    return result


def parse_property_pairs(html: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for key, value in re.findall(r'"(?:name|key)"\s*:\s*"([^"]{1,30})"\s*,\s*"(?:value|val)"\s*:\s*"([^"]{1,80})"', html):
        clean_key = clean_html_text(key)
        clean_value = clean_html_text(value)
        if is_useful_property_pair(clean_key, clean_value) and clean_key not in props and len(props) < 20:
            props[clean_key] = clean_value
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        cells = [clean_html_text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL)]
        cells = [cell for cell in cells if cell]
        for index in range(0, len(cells) - 1, 2):
            key, value = cells[index], cells[index + 1]
            if is_useful_property_pair(key, value) and key not in props and len(props) < 20:
                props[key] = value
    for key, value in re.findall(
        r'<div[^>]*(?:class|data-[^=]+)=["\'][^"\']*(?:property|attribute|attr|参数|pack-info)[^"\']*["\'][^>]*>(.*?)</div>\s*<div[^>]*>(.*?)</div>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        clean_key = clean_html_text(key)
        clean_value = clean_html_text(value)
        if is_useful_property_pair(clean_key, clean_value) and clean_key not in props and len(props) < 20:
            props[clean_key] = clean_value
    return props


def is_useful_property_pair(key: str, value: str) -> bool:
    key = clean_html_text(key)
    value = clean_html_text(value)
    if not key or not value:
        return False
    if len(key) > 40 or len(value) > 160:
        return False
    if re.search(r"https?://|登录|注册|收藏|分享|举报|客服|联系|下单|采购车", key + value, re.IGNORECASE):
        return False
    if re.search(r"近\d+天|代发|揽收率|铺货|分销商|下游铺货", key, re.IGNORECASE):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", key) or re.fullmatch(r"\d+(?:\.\d+)?", value):
        return False
    if key in {"长(cm)", "宽(cm)", "高(cm)", "体积(cm³)", "重量(g)"}:
        return False
    return True


def template_property_pairs(properties: dict[str, Any]) -> dict[str, str]:
    skip_key_pattern = (
        r"近\d+天|代发|揽收|铺货|分销商|下游铺货|"
        r"品牌|牌子|商标|Logo|logo|产地|生产地|厂家|厂名|工厂|源头|货号|款号|型号|编号|"
        r"材质|材料|面料|成分|包装|包裝|装箱|箱规|加工定制|货源类型|是否跨境货源|主要下游平台|主要销售地区|销售地区|"
        r"有可授权的自有品牌|有可授权的自由品牌|授权|是否跨境出口专供货源|专利类型|专利号|版权|"
        r"上市时间|上市年份|季节|价格段|专利|特許|進出口|进出口|进口|出口|外贸|外貿|认证|認證|质检|質檢|报告|報告|"
        r"跨境风格类型|主要下游销售地区"
    )
    skip_value_pattern = (
        r"1688|阿里巴巴|厂家|工厂|源头|批发|一件代发|代发|跨境|外贸|货源|品牌授权|授权|"
        r"专利|特許|版权|认证|质检|报告|主要下游平台|主要销售地区|出口|进口"
    )
    result: dict[str, str] = {}
    value_set = {clean_html_text(str(value)) for value in properties.values()}
    for key, value in properties.items():
        raw_key = clean_html_text(str(key))
        raw_value = clean_html_text(str(value))
        if re.search(skip_key_pattern, raw_key, re.IGNORECASE):
            continue
        clean_key = raw_key
        clean_value = raw_value
        if not clean_key or not clean_value:
            continue
        if clean_key in value_set:
            continue
        if re.search(skip_key_pattern, clean_key, re.IGNORECASE) or re.search(skip_value_pattern, clean_value, re.IGNORECASE):
            continue
        if len(result) < 30:
            result[clean_key] = clean_value
    return result


def parse_sku_rows(html: str, image_urls: list[str], fallback_price: str) -> list[dict[str, Any]]:
    sku_model_rows = parse_sku_model_rows(html, fallback_price)
    if sku_model_rows:
        return sku_model_rows
    values = [clean_html_text(item) for item in re.findall(r'"(?:name|value|specValue)"\s*:\s*"([^"]{1,40})"', html)]
    values = [
        item
        for item in values
        if item
        and not re.search(r"https?://|^\d+$|1688|TEMPLATED|MODULE|OFFER|LOGIN|LOGIN_ID", item, re.IGNORECASE)
        and not re.fullmatch(r"[A-Z_]{4,}", item)
        and not is_bad_sku_name(item)
    ]
    values = list(dict.fromkeys(values))[:80]
    if not values:
        return []
    return [
        {
            "spec1": clean_source_sku_name(value),
            "spec2": "",
            "price": fallback_price or "0",
            "stock": 100,
            "image_url": image_urls[index % len(image_urls)] if image_urls else "",
        }
        for index, value in enumerate(values)
    ]


def parse_shipping_fee(html: str) -> float:
    if not html:
        return 0.0

    if has_free_shipping_text(html):
        return 0.0

    for key in ("shippingServices", "logisticsModel", "freightTemplate", "freightInfo", "deliveryInfo"):
        shipping = extract_json_object_after_key(html, key)
        fee = first_shipping_fee_from_object(shipping)
        if fee is not None:
            return fee

    patterns = [
        r"(?:运费|邮费|配送费|快递|物流)[^。；，,\n]{0,20}(?:¥|￥)?\s*(0(?:\.0{1,2})?)\s*(?:起)?",
        r"(?:运费|快递|物流|配送费|邮费)[^0-9¥￥]{0,20}[¥￥]?\s*(\d+(?:\.\d+)?)",
        r"[¥￥]\s*(\d+(?:\.\d+)?)[^。；，,]{0,12}(?:运费|快递|物流|配送费|邮费)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            fee = safe_price(match.group(1))
            if 0 <= fee < 1000:
                return fee
    return 0.0


def has_free_shipping_text(value: str) -> bool:
    text = clean_html_text(value or "")
    return bool(
        re.search(r"(?:包邮|免运费|免邮|免配送费|送料無料|送料込み|free\s*shipping)", text, re.IGNORECASE)
        or re.search(r"(?:运费|邮费|配送费|快递|物流)[^。；，,\n]{0,20}(?:¥|￥)?\s*0(?:\.0{1,2})?\s*(?:起)?", text)
    )


def object_has_free_shipping(value: Any) -> bool:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key).lower()
                if key_text in {"freepostage", "freeshipping", "freefreight", "isfreepostage", "isfreeshipping"}:
                    if str(child).lower() in {"true", "1", "yes"}:
                        return True
                if isinstance(child, str) and has_free_shipping_text(child):
                    return True
                if isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str) and has_free_shipping_text(item):
            return True
    return False


def first_shipping_fee_from_object(value: Any) -> float | None:
    if value is None:
        return None
    if object_has_free_shipping(value):
        return 0.0
    fee_keys = {
        "freight",
        "freightFee",
        "freightPrice",
        "postFee",
        "postage",
        "shippingFee",
        "shippingPrice",
        "logisticsFee",
        "deliveryFee",
        "deliveryPrice",
        "carriage",
        "carriageFee",
        "expressFee",
        "expressPrice",
        "transportFee",
        "transportPrice",
        "postFeeValue",
    }
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key in fee_keys:
                    fee = safe_price(child)
                    if 0 <= fee < 1000:
                        return fee
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return None


def parse_sku_model_rows(html: str, fallback_price: str) -> list[dict[str, Any]]:
    sku_model = extract_json_object_after_key(html, "skuModel")
    if not isinstance(sku_model, dict):
        return []
    sku_info_map = sku_model.get("skuInfoMap") if isinstance(sku_model.get("skuInfoMap"), dict) else {}
    sku_props = sku_model.get("skuProps") if isinstance(sku_model.get("skuProps"), list) else []
    display_price = sku_scale_display_price(sku_model)
    prop_image_map = sku_prop_image_map(sku_props)
    rows: list[dict[str, Any]] = []
    used: set[str] = set()
    for raw_key, info in sku_info_map.items():
        spec_parts = sku_spec_parts(raw_key, info)
        if not spec_parts:
            continue
        spec1 = clean_source_sku_name(spec_parts[0])
        spec2 = clean_source_sku_name(spec_parts[1]) if len(spec_parts) > 1 else ""
        dedupe_key = f"{spec1}>{spec2}"
        if not spec1 or is_bad_sku_name(spec1) or dedupe_key in used:
            continue
        image_url = ""
        for part in spec_parts:
            image_url = prop_image_map.get(clean_html_text(part)) or image_url
        rows.append(
            {
                "spec1": spec1,
                "spec2": "" if spec2 == "標準" else spec2,
                "price": sku_price_from_info(info, fallback_price, display_price),
                "stock": sku_stock_from_info(info),
                "image_url": normalize_image_url(image_url),
            }
        )
        used.add(dedupe_key)
    if rows:
        return rows
    prop_values: list[dict[str, Any]] = []
    for prop in sku_props:
        if isinstance(prop, dict) and isinstance(prop.get("value"), list):
            prop_values.extend([item for item in prop["value"] if isinstance(item, dict)])
    if prop_values:
        for item in prop_values:
            raw_name = str(item.get("name") or "")
            spec_name = clean_source_sku_name(raw_name)
            if not spec_name or is_bad_sku_name(spec_name) or spec_name in used:
                continue
            info = sku_info_map.get(raw_name) or find_sku_info_by_name(sku_info_map, raw_name)
            price = sku_price_from_info(info, fallback_price, display_price)
            stock = sku_stock_from_info(info)
            rows.append(
                {
                    "spec1": spec_name,
                    "spec2": "",
                    "price": price,
                    "stock": stock,
                    "image_url": normalize_image_url(str(item.get("imageUrl") or "")),
                }
            )
            used.add(spec_name)
    if rows:
        return rows
    for raw_name, info in sku_info_map.items():
        spec_name = clean_source_sku_name(str(raw_name))
        if not spec_name or is_bad_sku_name(spec_name) or spec_name in used:
            continue
        rows.append(
            {
                "spec1": spec_name,
                "spec2": "",
                "price": sku_price_from_info(info, fallback_price, display_price),
                "stock": sku_stock_from_info(info),
                "image_url": "",
            }
        )
        used.add(spec_name)
    return rows


def extract_json_object_after_key(text: str, key: str) -> dict[str, Any] | None:
    key_match = re.search(r'"' + re.escape(key) + r'"\s*:', text)
    if not key_match:
        return None
    start = text.find("{", key_match.end())
    if start < 0:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def sku_prop_image_map(sku_props: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for prop in sku_props:
        if not isinstance(prop, dict):
            continue
        values = prop.get("value")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            name = clean_html_text(str(item.get("name") or ""))
            image_url = str(item.get("imageUrl") or item.get("image") or item.get("imageUrlBig") or "")
            if name and image_url:
                result[name] = normalize_image_url(image_url)
    return result


def sku_spec_parts(raw_key: Any, info: Any) -> list[str]:
    raw = str(raw_key or "")
    if isinstance(info, dict) and info.get("specAttrs"):
        raw = str(info.get("specAttrs"))
    raw = html_lib.unescape(raw).replace("&gt;", ">").replace("\\u003e", ">")
    return [clean_html_text(part) for part in re.split(r"\s*>\s*", raw) if clean_html_text(part)]


def find_sku_info_by_name(sku_info_map: dict[str, Any], raw_name: str) -> dict[str, Any]:
    for info in sku_info_map.values():
        if isinstance(info, dict) and str(info.get("specAttrs") or "") == raw_name:
            return info
    return {}


def sku_scale_display_price(sku_model: dict[str, Any]) -> str:
    for key in ("skuPriceScale", "priceRange", "priceScale"):
        value = sku_model.get(key)
        if value in (None, ""):
            continue
        numbers = [safe_price(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value))]
        numbers = [item for item in numbers if item > 0]
        if numbers:
            return f"{max(numbers):.2f}"
    return ""


def sku_price_from_info(info: Any, fallback_price: str, display_price: str = "") -> str:
    if isinstance(info, dict):
        for key in (
            "price",
            "salePrice",
            "offerPrice",
            "discountPrice",
            "promotionPrice",
            "wholesalePrice",
            "retailPrice",
            "originalPrice",
        ):
            value = info.get(key)
            if value not in (None, "") and safe_price(value) > 0:
                return str(value)
        for child_key in ("priceInfo", "saleInfo", "tradeInfo", "skuPrice", "priceRange"):
            child = info.get(child_key)
            if isinstance(child, dict):
                child_price = sku_price_from_info(child, "", "")
                if safe_price(child_price) > 0:
                    return child_price
    if display_price:
        return display_price
    return fallback_price or "0"


def sku_stock_from_info(info: Any) -> int:
    if isinstance(info, dict):
        for key in ("canBookCount", "stock", "amount", "saleCount"):
            value = info.get(key)
            try:
                number = int(float(value))
                if key == "saleCount":
                    continue
                return max(number, 0)
            except (TypeError, ValueError):
                pass
    return 100

def clean_source_sku_name(value: str) -> str:
    value = clean_html_text(value or "")
    value = re.sub(r"(BENNUO|本诺|本諾|冷刃|COLD)", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"[\[\]【】()（）]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_/|｜,，;；")
    return value

def is_bad_sku_name(value: str) -> bool:
    normalized = re.sub(r"\s+", "", clean_html_text(value))
    bad_exact = {
        "立即下单", "加采购车", "材质", "品牌", "形状", "风格", "货号", "图案", "价格段",
        "是否进口", "产品质量等级", "产品上市时间", "颜色", "尺码", "默认", "请选择", "全部",
        "产地", "是否有专利", "主要下游平台", "主要销售地区", "有可授权的自有品牌",
        "是否出口货源", "是否插电", "是否可降解", "加工定制", "包装", "适用范围", "专利类型",
        "专利号", "版权", "外贸出口认证", "质检报告编号", "是否跨境出口专供货源",
    }
    if normalized in bad_exact:
        return True
    if re.fullmatch(r"是否.+", normalized) or re.fullmatch(r"主要.+", normalized):
        return True
    return bool(re.search(r"下单|采购车|属性|批量|收藏|分享|登录|注册|客服|联系|举报|库存|重量|尺寸|产地|专利|认证|报告|授权|出口|进口|平台|地区", normalized))

def simplify_sku_name(value: str, target_language: str = "ja") -> str:
    value = sanitize_listing_copy(value or "")
    value = re.sub(r"[\[\]【】()（）]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value or is_bad_sku_name(value) or is_garbled_sku_spec(value):
        return target_language_meta(target_language)["standard_sku"]
    value = translate_common_sku_name(value)
    value = localize_sku_name(value, target_language)
    return truncate_sku_name(value, 20) if value else target_language_meta(target_language)["standard_sku"]


def sku_translation_preserves_critical_tokens(source: str, mapped: str) -> bool:
    source_text = clean_html_text(source or "").lower()
    mapped_text = clean_html_text(mapped or "").lower()
    critical_groups = (
        (("pp袋", "pp 袋", "pp袋装", "pp袋裝"), ("pp袋", "pp")),
        (("盒装", "盒裝", "盒子装", "盒子裝"), ("箱入り", "箱", "盒")),
        (("袋装", "袋裝"), ("袋入り", "袋")),
        (("白色", "白"), ("ホワイト", "白", "white")),
        (("黑色", "黒色", "黑", "黒"), ("ブラック", "黒", "黑", "black")),
        (("灰色", "灰"), ("グレー", "灰", "gray", "grey")),
        (("红色", "紅色", "红", "紅"), ("レッド", "赤", "red")),
        (("绿色", "綠色", "绿", "綠"), ("グリーン", "緑", "green")),
        (("蓝色", "藍色", "蓝", "藍"), ("ブルー", "青", "blue")),
        (("黄色", "黄"), ("イエロー", "黄", "yellow")),
    )
    for source_tokens, mapped_tokens in critical_groups:
        if any(token.lower() in source_text for token in source_tokens) and not any(token.lower() in mapped_text for token in mapped_tokens):
            return False
    return True


def truncate_sku_name(value: str, limit: int = 20) -> str:
    value = re.sub(r"\s+", " ", clean_html_text(value or "")).strip()
    if len(value) <= limit:
        return value
    tokens = value.split(" ")
    parts: list[str] = []
    for token in tokens:
        candidate = " ".join(parts + [token]).strip()
        if len(candidate) > limit:
            break
        parts.append(token)
    size_token = next((token for token in tokens if re.fullmatch(r"\d+(?:\.\d+)?m", token, re.IGNORECASE)), "")
    if size_token and size_token not in parts:
        candidate_parts = parts[:]
        while candidate_parts and len(" ".join(candidate_parts + [size_token])) > limit:
            candidate_parts.pop()
        if len(" ".join(candidate_parts + [size_token])) <= limit:
            parts = candidate_parts + [size_token]
    if parts:
        return " ".join(parts)
    return value[:limit]


def is_garbled_sku_spec(value: str) -> bool:
    value = clean_html_text(value or "")
    if not value:
        return True
    meaningful = re.sub(r"[\s+\-_/|｜,，;；.0-9]+", "", value)
    if not meaningful:
        return True
    return False


def fallback_sku_name_from_index(raw_spec: str, index: int, target_language: str = "ja") -> str:
    raw = clean_html_text(raw_spec or "")
    decimal_size = re.search(r"(?:^|[^\d])(\d+\.\d+)\s*(?:m|米)?(?:$|[^\d])", raw, re.IGNORECASE)
    explicit_size = re.search(r"(?:^|[^\d])(\d+)\s*(?:m|米)(?:$|[^\d])", raw, re.IGNORECASE)
    size_value = decimal_size.group(1) if decimal_size else (explicit_size.group(1) if explicit_size else "")
    size = f"{size_value}m" if size_value else ""
    if normalize_target_language(target_language) == "en":
        return f"Set {index}{(' ' + size) if size else ''}"[:20]
    return f"セット{index}{(' ' + size) if size else ''}"[:20]


def translate_common_sku_name(value: str) -> str:
    replacements = {
        "pp袋": "PP袋",
        "PP袋": "PP袋",
        "pp 袋": "PP袋",
        "盒装": "箱入り",
        "盒裝": "箱入り",
        "袋装": "袋入り",
        "袋裝": "袋入り",
        "钓鱼椅": "釣り椅子",
        "钓椅": "釣り椅子",
        "工具包": "工具バッグ",
        "靠背": "背もたれ",
        "背包套装": "リュックセット",
        "背包": "リュック",
        "套装": "セット",
        "入门": "入門",
        "基础": "基本",
        "双炮台": "竿受け2個",
        "炮台": "竿受け",
        "支架": "スタンド",
        "鱼护": "魚キープ網",
        "遮阳": "日よけ",
        "钓伞": "釣り傘",
        "拉饵盘": "エサ皿",
        "多功能": "多機能",
        "防刮耐磨": "傷に強い",
        "架双竿": "2本竿用",
        "轻量款": "軽量タイプ",
        "仅重": "軽量",
        "黑武士": "ブラック",
        "冷刃": "",
        "本诺": "",
        "本諾": "",
        "BENNUO": "",
        "COLD": "",
        "红色": "レッド",
        "紅色": "レッド",
        "绿色": "グリーン",
        "綠色": "グリーン",
        "蓝色": "ブルー",
        "藍色": "ブルー",
        "青色": "ブルー",
        "灰色": "グレー",
        "灰": "グレー",
        "黄色": "イエロー",
        "橙色": "オレンジ",
        "粉色": "ピンク",
        "棕色": "ブラウン",
        "咖啡色": "ブラウン",
        "紫色": "パープル",
        "白色": "ホワイト",
        "黑色": "ブラック",
        "小号": "小サイズ",
        "中号": "中サイズ",
        "大号": "大サイズ",
        "小サイズ": "小サイズ",
        "三层": "3段",
        "四层": "4段",
        "五层": "5段",
        "星星款": "スター",
        "苹果款": "アップル",
        "星星": "スター",
        "苹果": "アップル",
        "电动感应水母": "クラゲ",
        "感应水母": "クラゲ",
        "水母": "クラゲ",
        "跳舞八爪鱼": "タコ",
        "八爪鱼": "タコ",
        "章鱼": "タコ",
        "鲨鱼": "サメ",
        "鲍鱼": "アワビ",
        "喷雾": "ミスト",
        "電池版": "電池式",
        "电池版": "電池式",
        "发条": "ゼンマイ",
        "灯光": "ライト付き",
        "蝴蝶结": "リボン",
        "幻彩": "カラフル",
        "默认": "標準",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"\s+", " ", value).strip()


def localize_japanese_sku_name(value: str) -> str:
    raw = clean_html_text(value or "")
    if not raw:
        return "標準"
    raw = re.sub(r"(BENNUO|本诺|本諾|冷刃|COLD)", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"[-_/|｜,，;；]+", " ", raw)
    raw = re.sub(r"\b\d+(?:\.\d+)?\s*(?:g|kg|克|斤)\b", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(
        r"(英文|日文|中文|手提|包装|包裝|厨房|专利|專利|特許|授权|授權|跨境|出口|外贸|货源|貨源|厂家|工厂|批发|批發|export|factory|wholesale|supplier)",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return "標準"

    color_tokens = [
        "レッド",
        "グリーン",
        "ブルー",
        "イエロー",
        "オレンジ",
        "ピンク",
        "ブラウン",
        "パープル",
        "グレー",
        "ホワイト",
        "ブラック",
    ]
    size_tokens = ["小サイズ", "中サイズ", "大サイズ"]
    product_tokens = ["釣り椅子", "クラゲ", "タコ", "サメ", "アワビ", "スター", "アップル"]
    variant_tokens = [
        "工具バッグ",
        "PP袋",
        "箱入り",
        "袋入り",
        "背もたれ",
        "リュックセット",
        "リュック",
        "入門",
        "基本",
        "竿受け2個",
        "竿受け",
        "スタンド",
        "魚キープ網",
        "日よけ",
        "釣り傘",
        "エサ皿",
        "多機能",
        "傷に強い",
        "2本竿用",
        "軽量タイプ",
        "軽量",
        "セット",
        "ブラック",
        "リボン",
        "カラフル",
        "ミスト",
        "電池式",
        "ゼンマイ",
        "ライト付き",
    ]

    parts: list[str] = []
    for token_group in (product_tokens, variant_tokens, size_tokens, color_tokens):
        for token in token_group:
            if token in raw and token not in parts:
                parts.append(token)
    if "リュックセット" in parts:
        parts = [token for token in parts if token not in {"リュック", "セット"}]
    if "竿受け2個" in parts:
        parts = [token for token in parts if token != "竿受け"]

    size_tokens_found = re.findall(r"\d+(?:\.\d+)?\s*m", raw, flags=re.IGNORECASE)
    if parts or size_tokens_found:
        low_priority_tokens = {"ブラック"}
        ordered_parts = [token for token in parts if token not in low_priority_tokens]
        ordered_parts.extend(item.replace(" ", "") for item in size_tokens_found)
        ordered_parts.extend(token for token in parts if token in low_priority_tokens)
        return " ".join(ordered_parts[:4])

    cleaned = re.sub(r"[A-Za-z]+", " ", raw)
    cleaned = re.sub(r"[\u4e00-\u9fff]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "標準"


def localize_sku_name(value: str, target_language: str = "ja") -> str:
    language = normalize_target_language(target_language)
    if language == "ja":
        return localize_japanese_sku_name(value)
    raw = clean_html_text(value or "")
    raw = re.sub(r"[-_/|｜,，;；]+", " ", raw)
    raw = re.sub(r"\b\d+(?:\.\d+)?\s*(?:g|kg|克|斤)\b", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(
        r"(英文|日文|中文|手提|包装|包裝|厨房|专利|專利|特許|授权|授權|跨境|出口|外贸|货源|貨源|厂家|工厂|批发|批發|export|factory|wholesale|supplier)",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(r"\s+", " ", raw).strip()
    if contains_cjk(raw):
        return target_language_meta(language)["standard_sku"]
    return raw or target_language_meta(language)["standard_sku"]


def image_failure_diagnostics(
    errors: list[str],
    *,
    main_source_count: int,
    detail_source_count: int,
    sku_source_count: int = 0,
    main_count: int,
    detail_count: int,
    sku_count: int = 0,
    main_target: int,
    detail_target: int,
    sku_target: int = 0,
    uploaded: bool,
    processed_count: int,
) -> list[str]:
    text = "\n".join(errors)
    diagnostics: list[str] = []
    if main_count <= 0:
        diagnostics.append("诊断：主图处理/上传后为空，商品无法生成可用主图。")
    elif main_count < main_target:
        if main_source_count < main_target:
            diagnostics.append(f"诊断：1688/Oxylabs 只解析到主图源图 {main_source_count}/{main_target}；按当前规则允许主图不足 5 张继续上架，并会尽量用干净 SKU/详情图或重复链接补足模板。")
        else:
            diagnostics.append(f"诊断：主图源图足够，但处理后只剩 {main_count}/{main_target}；按当前规则允许继续上架。")
    if detail_count == 0 and detail_source_count > 0:
        diagnostics.append("诊断：详情图已解析到源图但处理后为 0；当前详情图不做数量限制，不会单独阻断流程，可按日志排查翻译/擦除/过滤原因。")
    if sku_target and sku_count < sku_target:
        diagnostics.append(f"诊断：有源图的 SKU 需要保留对应 SKU 图，但处理/上传后只剩 {sku_count}/{sku_target}，主要排查 SKU 图文字/水印/Logo/二维码/联系方式擦除失败、MediaKit 稳定性或妙手图片空间上传。")
    if "AI MediaKit 未配置" in text or "图片翻译未配置" in text:
        diagnostics.append("诊断：AI MediaKit 未配置或未启用，请检查 Doubao-Seed-Translation/AI MediaKit API Key、模型配置状态和服务地址。")
    if "AbilityProcessingError" in text or "fail to run workflow" in text or "HTTP 500" in text:
        diagnostics.append("诊断：AI MediaKit 返回 500/workflow 失败，属于 MediaKit 工作流处理失败；可更换 MediaKit 能力/模型、降低并发、重试，或用其他图片处理模型替代。")
    if "UNEXPECTED_EOF" in text or "SSLEOFError" in text or "Max retries exceeded" in text:
        diagnostics.append("诊断：AI MediaKit 请求出现 SSL/连接中断，优先排查本机网络、火山接口稳定性、代理/TLS，必要时增加重试或更换服务。")
    if "800013" in text or "resolution not supported" in text or "image resolution not supported" in text:
        diagnostics.append("诊断：MediaKit 不支持原图尺寸，系统已允许本地压缩/缩放后重试；如果仍失败，需要继续降低尺寸/体积或更换支持该尺寸的模型。")
    if "视觉模型未配置" in text or "快速图片判断失败" in text:
        diagnostics.append("诊断：视觉判断模型不可用或失败，系统会保守走 MediaKit；如误删/漏判较多，请更换或配置更稳定的视觉模型。")
    if "画面无对应" in text or "供应链宣传图" in text or "无效详情图" in text or "不包含商品主体" in text or "纯尺寸图" in text or "纯功能说明图" in text:
        diagnostics.append("诊断：部分图片被判定不是可上架商品实物图；如判断不准，需要调整详情图过滤规则或更换视觉模型。")
    if "妙手图片空间上传失败" in text or (processed_count > 0 and not uploaded):
        diagnostics.append("诊断：图片已处理但上传妙手图片空间失败，请检查妙手登录状态、图片空间接口、网络或妙手账号权限。")
    if main_count <= 0 or (sku_target and sku_count < sku_target):
        diagnostics.append("最终阻断点：主图为空或 SKU 图数量未达标，已按要求停止流程，不生成妙手模板，也不会自动导入妙手。")
    return diagnostics


def prepare_compliant_images(
    task_id: str,
    product: dict[str, Any],
    image_mode: str = "fast",
    target_language: str = "ja",
    before_image_upload_callback: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    settings = image_mode_settings(image_mode)
    main_target = int(settings["main_target"])
    detail_target = int(settings["detail_target"])
    main_limit = int(settings["main_limit"])
    detail_limit = int(settings["detail_limit"])
    image_workers = int(settings["workers"])
    use_seedream = False
    main_source_urls = unique_urls(product.get("main_images", []) or [])[:main_limit]
    main_source_set = set(main_source_urls)
    raw_detail_source_urls = unique_urls(product.get("detail_images", []) or [])
    detail_source_urls = [url for url in raw_detail_source_urls if url not in main_source_set][:detail_limit]
    if not detail_source_urls and raw_detail_source_urls:
        detail_source_urls = raw_detail_source_urls[:detail_limit]
    sku_source_items = [
        (sku_identity(sku), normalize_image_url(str(sku.get("image_url") or "")))
        for sku in product.get("skus", []) or []
    ]
    image_urls = unique_urls(main_source_urls + detail_source_urls + [url for _key, url in sku_source_items if url])
    if not image_urls and not main_source_urls:
        return {"ok": False, "url_map": {}, "notice": "未解析到商品图片，模板将不填写处理图。", "errors": ["no_images"]}

    local_dir = RUNTIME_DIR / "images" / task_id
    local_dir.mkdir(parents=True, exist_ok=True)
    url_map: dict[str, str] = {}
    main_keys: list[str] = []
    detail_keys: list[str] = []
    sku_keys: dict[str, str] = {}
    errors: list[str] = []
    processed_items: list[dict[str, Any]] = []
    image_signatures: dict[str, list[int]] = {"all": [], "main": [], "detail": [], "sku": []}
    sku_signature_keys: list[tuple[int, str]] = []
    progress_state = {"done": 0, "total": 1}

    def set_progress_total(total: int) -> None:
        progress_state["total"] = max(1, total)

    def bump_progress(message_prefix: str = "正在处理图片") -> None:
        progress_state["done"] = min(progress_state["done"] + 1, progress_state["total"])
        if progress_callback:
            progress_callback(progress_state["done"], progress_state["total"])
        if status_callback:
            percent = 35 + round((progress_state["done"] / max(progress_state["total"], 1)) * 45)
            status_callback(f"{message_prefix} {progress_state['done']}/{progress_state['total']}", percent)

    def add_processed(key: str, path: Path, role: str, sku_key: str = "") -> None:
        signature = image_signature(path)
        if role == "sku" and signature is not None:
            for old_signature, old_key in sku_signature_keys:
                if image_signature_distance(signature, old_signature) <= 5:
                    if sku_key:
                        sku_keys[sku_key] = old_key
                    return
        role_signatures = image_signatures.setdefault(role, [])
        comparison_signatures = role_signatures
        if signature is not None and any(image_signature_distance(signature, old) <= 5 for old in comparison_signatures):
            return
        if signature is not None:
            role_signatures.append(signature)
            if role == "sku":
                sku_signature_keys.append((signature, key))
        processed_items.append({"key": key, "path": path, "role": role, "sku_key": sku_key})
        if role == "main" and key not in main_keys:
            main_keys.append(key)
        elif role == "detail" and key not in detail_keys:
            detail_keys.append(key)
        elif role == "sku" and sku_key:
            sku_keys[sku_key] = key

    def process_image_job(job: dict[str, Any]) -> dict[str, Any]:
        result = process_one_image_v2(
            str(job["source_url"]),
            Path(job["path"]),
            product,
            role=str(job["role"]),
            sku_text=str(job.get("sku_key") or ""),
            label_variant=int(job.get("index") or 1),
            use_seedream=use_seedream,
            target_language=target_language,
            task_id=task_id,
            source_image_url=str(job["source_url"]),
        )
        return {**job, "result": result}

    def run_image_jobs(jobs: list[dict[str, Any]], label: str, action_label: str) -> None:
        if not jobs:
            return
        max_workers = min(image_workers, len(jobs))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(process_image_job, job): job for job in jobs}
            for future in as_completed(future_map):
                job = future_map[future]
                image_url = str(job.get("source_url") or job.get("key") or "")
                try:
                    finished = future.result()
                    process_result = finished.get("result") or {}
                    if not process_result.get("keep", True):
                        errors.append(f"已删除{label}：{process_result.get('reason') or image_url}")
                        continue
                    add_processed(
                        str(finished["key"]),
                        Path(finished["path"]),
                        str(finished["role"]),
                        sku_key=str(finished.get("sku_key") or ""),
                    )
                except AutoPublishError as exc:
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(f"{label}处理失败：{image_url} {exc}")
                finally:
                    bump_progress(action_label)

    def prefilter_detail_urls(source_urls: list[str]) -> list[str]:
        selected: list[str] = []
        for image_url in source_urls[:DETAIL_IMAGE_SCAN_LIMIT]:
            if len(selected) >= DETAIL_IMAGE_OUTPUT_LIMIT:
                break
            try:
                image_bytes = download_1688_image(image_url)
                image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGBA")
            except (requests.RequestException, OSError, UnidentifiedImageError) as exc:
                errors.append(f"详情图预筛下载/识别失败，已跳过：{image_url} {exc}")
                continue
            delete_reason = detect_supply_chain_promo_image(image, product, task_id=task_id)
            if delete_reason:
                errors.append(f"已预筛删除不适合上架的详情图：{delete_reason}")
                continue
            selected.append(image_url)
        if source_urls and not selected:
            errors.append("详情图预筛后没有可用图片；详情图不设最低数量限制，流程会继续检查主图和SKU图。")
        return selected

    main_jobs = [
        {"key": image_url, "source_url": image_url, "path": local_dir / f"main_{index:02d}.jpg", "role": "main", "index": index}
        for index, image_url in enumerate(main_source_urls[:main_limit], start=1)
    ]
    sku_jobs: list[dict[str, Any]] = []
    missing_sku_items: list[tuple[int, str]] = []
    sku_reuse_groups: dict[str, str] = {}
    for index, (sku_key, image_url) in enumerate(sku_source_items[:40], start=1):
        if not sku_key:
            continue
        sku_group = sku_image_group_key(sku_key)
        if sku_group in sku_reuse_groups:
            sku_keys[sku_key] = sku_reuse_groups[sku_group]
            continue
        output_path = local_dir / f"sku_{len(sku_reuse_groups) + 1:02d}.jpg"
        generated_key = f"generated:sku:{sku_group}"
        sku_reuse_groups[sku_group] = image_url or generated_key
        if image_url:
            sku_jobs.append(
                {
                    "key": image_url,
                    "source_url": image_url,
                    "path": output_path,
                    "role": "sku",
                    "sku_key": sku_key,
                    "index": len(sku_reuse_groups),
                }
            )
        else:
            missing_sku_items.append((len(sku_reuse_groups), sku_key))
            sku_keys[sku_key] = generated_key

    initial_total = len(main_jobs) + len(detail_source_urls[:detail_limit]) + len(sku_jobs)
    set_progress_total(initial_total)
    if progress_callback:
        progress_callback(0, progress_state["total"])
    run_image_jobs(main_jobs, "主图", "正在擦除主图")

    if status_callback and detail_source_urls:
        status_callback("正在预筛详情图", 58)
    detail_source_urls = prefilter_detail_urls(detail_source_urls)
    detail_jobs = [
        {"key": image_url, "source_url": image_url, "path": local_dir / f"detail_{index:02d}.jpg", "role": "detail", "index": index}
        for index, image_url in enumerate(detail_source_urls[:DETAIL_IMAGE_OUTPUT_LIMIT], start=1)
    ]
    run_image_jobs(detail_jobs, "详情图", "正在翻译详情图")

    run_image_jobs(sku_jobs, "SKU图", "正在擦除SKU图")

    for _index, sku_key in missing_sku_items:
        errors.append(f"提示：SKU `{sku_key}` 在 1688 未提供源图，不作为失败条件；按要求不自动生成补图。")

    def promote_images_to_main(source_role: str, source_keys: list[str], source_label: str) -> int:
        promoted = 0
        for source_key in list(source_keys):
            if len(main_keys) >= main_target:
                break
            source_item = next((item for item in processed_items if item["key"] == source_key and item["role"] == source_role), None)
            if not source_item:
                continue
            promoted_key = f"promoted-main:{source_role}:{source_key}"
            promoted_path = local_dir / f"main_from_{source_role}_{len(main_keys) + 1:02d}.jpg"
            try:
                shutil.copyfile(Path(source_item["path"]), promoted_path)
            except OSError as exc:
                errors.append(f"{source_label}补主图失败：{source_key} {exc}")
                continue
            before_count = len(main_keys)
            add_processed(promoted_key, promoted_path, "main")
            if len(main_keys) > before_count:
                promoted += 1
        return promoted

    if len(main_keys) < main_target:
        sku_promoted = promote_images_to_main("sku", list(sku_keys.values()), "SKU图")
        detail_promoted = promote_images_to_main("detail", detail_keys, "详情图")
        if sku_promoted or detail_promoted:
            errors.append(
                f"主图不足时已用干净图片补充主图：SKU图 {sku_promoted} 张，详情图 {detail_promoted} 张，未使用 AI 生成补图。"
            )
    if len(main_keys) < main_target:
        errors.append(f"提示：主图可用数量 {len(main_keys)}/{main_target}，按要求允许继续上架；后续会重复已有干净图片链接补足模板主图。")

    main_order = {url: index for index, url in enumerate(main_source_urls)}
    detail_order = {url: index for index, url in enumerate(detail_source_urls)}
    main_fallback_order = {key: index for index, key in enumerate(list(main_keys))}
    detail_fallback_order = {key: index for index, key in enumerate(list(detail_keys))}
    main_keys.sort(key=lambda key: main_order.get(key, 1000 + main_fallback_order.get(key, 0)))
    detail_keys.sort(key=lambda key: detail_order.get(key, 1000 + detail_fallback_order.get(key, 0)))

    processed_paths = [item["path"] for item in processed_items]
    if processed_paths:
        try:
            if before_image_upload_callback:
                if status_callback:
                    status_callback("正在打开妙手，请手动完成验证码", 80)
                before_image_upload_callback()
            if status_callback:
                status_callback("正在上传图片到妙手图片空间", 81)
            uploaded_map = upload_images_to_miaoshou_picture_space(processed_paths, task_id=task_id)
            for item in processed_items:
                if item["path"] in uploaded_map:
                    url_map[item["key"]] = uploaded_map[item["path"]]
                else:
                    if item.get("role") == "sku" and item.get("sku_key"):
                        errors.append(f"SKU图上传妙手图片空间失败：`{item['sku_key']}` 对应文件 {item['path'].name} 未返回图片地址。")
                    else:
                        errors.append(f"妙手图片空间上传失败：{item['path'].name} 未返回图片地址。")
        except AutoPublishError as exc:
            errors.append(f"妙手图片空间上传失败：{exc}")
            url_map = {}
    main_images = [url_map[key] for key in main_keys if key in url_map][:main_target]
    detail_images = [url_map[key] for key in detail_keys if key in url_map][:DETAIL_IMAGE_OUTPUT_LIMIT]
    sku_image_map = {sku_key: url_map[key] for sku_key, key in sku_keys.items() if key in url_map}
    fallback_main_pool = [
        url
        for url in (
            main_images
            + [url_map[key] for key in sku_keys.values() if key in url_map]
            + [url_map[key] for key in detail_keys if key in url_map]
        )
        if is_importable_image_url(str(url or ""))
    ]
    if main_images and len(main_images) < main_target and fallback_main_pool:
        repeat_index = 0
        while len(main_images) < main_target and fallback_main_pool:
            main_images.append(fallback_main_pool[repeat_index % len(fallback_main_pool)])
            repeat_index += 1
        errors.append(f"主图不足 5 张，已按要求重复已有干净图片链接补足到 {len(main_images)} 张。")
    notice = (
        f"图片已按角色处理并上传妙手图片空间：主图 {len(main_images)} 张，详情图 {len(detail_images)} 张，SKU图 {len(sku_image_map)} 张。"
        "合规原图会直接标准化使用；需处理的图片已按规则清理/翻译；处理失败的原图不会兜底进模板；按当前规则不再自动生成补图。"
        if url_map
        else "图片处理或上传失败；合规原图可直接使用，但处理失败的原图不会兜底进模板，请人工复核。"
    )
    for diagnostic in image_failure_diagnostics(
        errors,
        main_source_count=len(main_source_urls),
        detail_source_count=len(detail_source_urls),
        sku_source_count=len([url for _key, url in sku_source_items[:40] if url]),
        main_count=len(main_images),
        detail_count=len(detail_images),
        sku_count=len(sku_image_map),
        main_target=main_target,
        detail_target=detail_target,
        sku_target=len([sku for sku in product.get("skus", [])[:20] if not is_bad_sku_name(str(sku.get("spec1") or "")) and normalize_image_url(str(sku.get("image_url") or ""))]),
        uploaded=bool(url_map),
        processed_count=len(processed_paths),
    ):
        if diagnostic not in errors:
            errors.append(diagnostic)
    return {
        "ok": bool(url_map),
        "url_map": url_map,
        "main_images": main_images,
        "detail_images": detail_images,
        "sku_image_map": sku_image_map,
        "notice": notice,
        "errors": errors,
        "local_dir": str(local_dir),
    }


def role_image_label(role: str) -> str:
    return {"main": "主图", "detail": "详情图", "sku": "SKU图"}.get(role, "图片")


def image_signature(path: Path) -> int | None:
    try:
        image = Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    except (OSError, UnidentifiedImageError):
        return None
    pixels = list(image.getdata())
    avg = sum(pixels) / max(len(pixels), 1)
    signature = 0
    for index, pixel in enumerate(pixels):
        if pixel >= avg:
            signature |= 1 << index
    return signature


def image_signature_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def sku_identity(sku: dict[str, Any]) -> str:
    spec1 = clean_html_text(str(sku.get("spec1") or ""))
    spec2 = clean_html_text(str(sku.get("spec2") or ""))
    return ">".join([part for part in (spec1, spec2) if part])


def sku_image_group_key(sku_key: str) -> str:
    parts = [clean_html_text(part) for part in str(sku_key or "").split(">") if clean_html_text(part)]
    if not parts:
        return "標準"
    size_pattern = re.compile(r"^(?:xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|均码|均碼|フリー|free|one size|\\d{2,3}(?:cm)?|\\d+号)$", re.IGNORECASE)
    non_size = [part for part in parts if not size_pattern.fullmatch(part.strip())]
    return non_size[0] if non_size else parts[0]


def process_one_image_v2(
    image_url: str,
    output_path: Path,
    product: dict[str, Any],
    role: str = "main",
    sku_text: str = "",
    label_variant: int = 1,
    use_seedream: bool = True,
    target_language: str = "ja",
    task_id: str = "",
    source_image_url: str = "",
) -> dict[str, Any]:
    try:
        image_bytes = download_1688_image(image_url)
    except requests.RequestException as exc:
        raise AutoPublishError(f"图片下载失败：{image_url} {exc}") from exc
    try:
        image = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise AutoPublishError(f"图片无法识别：{image_url}") from exc

    if role == "detail":
        promo_reason = detect_supply_chain_promo_image(image, product, task_id=task_id)
        if promo_reason:
            return {"keep": False, "reason": promo_reason, "editor": "promo_filter"}
    if not use_seedream:
        return process_image_low_cost(
            image,
            output_path,
            product,
            role=role,
            sku_text=sku_text,
            target_language=target_language,
            task_id=task_id,
            source_image_url=source_image_url or image_url,
        )
    analysis = analyze_image_compliance(image, product)
    if role == "detail":
        analysis = translate_analysis_text_regions(analysis, product)
    seedream_result = edit_image_with_seedream(
        image,
        output_path,
        product,
        analysis,
        role=role,
        sku_text=sku_text,
        label_variant=label_variant,
    )
    if seedream_result.get("ok"):
        return {"keep": True, "analysis": analysis, "editor": "seedream"}

    if analysis.get("keep") is False and role == "detail":
        delete_reason = deletion_reason_if_factory_or_pure_text(analysis)
        if delete_reason:
            return {"keep": False, "reason": delete_reason, "analysis": analysis, "editor": "promo_filter"}
    if requires_ai_regeneration(analysis):
        reason = "图片含中文/人脸/Logo/水印等风险区域，Seedream 未成功生成合规新图。"
        if seedream_result.get("error"):
            reason = f"{reason} {seedream_result['error']}"
        raise AutoPublishError(reason)
    if seedream_result.get("error") and not analysis:
        raise AutoPublishError(f"Seedream 未成功生成参考新图，且视觉分析不可用。{seedream_result['error']}")
    heavy_text_overlay = has_heavy_text_overlay(analysis, image.size)
    edited = apply_compliance_edits(image, analysis, relocate_text=heavy_text_overlay)
    final_image = enhance_product_image(edited, captions=[], role=role)
    save_standard_product_image(final_image, output_path, role=role, quality=92)
    result = {"keep": True, "analysis": analysis, "editor": "local"}
    if seedream_result.get("error"):
        result["seedream_error"] = seedream_result["error"]
    return result


def download_1688_image(image_url: str) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://detail.1688.com/",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.45,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    candidates = alicdn_image_url_candidates(image_url)
    errors: list[str] = []
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8))
        session.mount("http://", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8))
        for candidate in candidates:
            try:
                response = session.get(candidate, timeout=(20, 90), headers=headers)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not response.content or (content_type and "image" not in content_type):
                    raise requests.RequestException(f"返回内容不是图片：{content_type or 'unknown'}")
                return response.content
            except requests.RequestException as exc:
                errors.append(f"{candidate}: {exc}")
    raise requests.RequestException("；".join(errors[-3:]) or image_url)


def mediakit_translate_tool_version(analysis: dict[str, Any]) -> str:
    if analysis.get("has_dense_text") is True or analysis.get("dense_text") is True:
        return "dense-text-translation"
    reason = str(analysis.get("reason") or "").lower()
    text_regions = [item for item in (analysis.get("text_regions") or []) if isinstance(item, dict)]
    dense_tokens = (
        "dense",
        "密集",
        "多段",
        "参数",
        "表格",
        "尺寸",
        "规格",
        "说明",
        "功能",
        "卖点",
        "細かい",
    )
    if len(text_regions) >= 4 or any(token in reason for token in dense_tokens):
        return "dense-text-translation"
    return "erase"


def mediakit_translate_source_lang(analysis: dict[str, Any]) -> str:
    has_cjk = analysis_has_cjk_text(analysis)
    has_latin = analysis_has_latin_text(analysis)
    if has_cjk and not has_latin:
        return "zh"
    if has_latin and not has_cjk:
        return "en"
    return ""


def build_mediakit_translate_payload(image_url: str, target_language: str, analysis: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "image_url": image_url,
        "target_lang": target_language_meta(target_language)["mediakit"],
        "tool_version": mediakit_translate_tool_version(analysis),
        "output_format": "jpeg",
    }
    source_lang = mediakit_translate_source_lang(analysis)
    if source_lang:
        payload["source_lang"] = source_lang
    return payload


def translate_detail_image_with_aimediakit(
    image: Image.Image,
    output_path: Path,
    role: str = "detail",
    target_language: str = "ja",
    task_id: str = "",
    source_image_url: str = "",
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = get_default_model_config_for_translation()
    if not config or not config.api_key_encrypted:
        return {"ok": False, "error": "AI MediaKit 图片翻译未配置：请配置 Doubao-Seed-Translation API Key。"}
    endpoint = config.base_url or AIMEDIAKIT_IMAGE_TRANSLATE_URL
    try:
        image_url = prepare_mediakit_image_url(image, task_id, output_path, "translate", source_image_url)
    except AutoPublishError as exc:
        return {"ok": False, "error": f"AI MediaKit 图片翻译输入图准备失败：{exc}"}
    payload = build_mediakit_translate_payload(image_url, target_language, analysis or {})
    try:
        payload = post_aimediakit_tool(
            endpoint,
            config.api_key_encrypted,
            payload,
            task_id=task_id,
            purpose="aimediakit_translate_image_text",
            model=config.model_name or "AI MediaKit",
            meta=model_config_usage_meta(config),
        )
    except requests.RequestException as exc:
        first_error = sanitize_secret_error(str(exc))
        if source_image_url and should_retry_mediakit_with_local_image(first_error):
            try:
                local_payload = {
                    **build_mediakit_translate_payload(
                        image_url_for_mediakit(image, task_id, output_path, "translate_retry"),
                        target_language,
                        analysis or {},
                    ),
                }
                payload = post_aimediakit_tool(
                    endpoint,
                    config.api_key_encrypted,
                    local_payload,
                    task_id=task_id,
                    purpose="aimediakit_translate_image_text",
                    model=config.model_name or "AI MediaKit",
                    meta=model_config_usage_meta(config, {"retry_input": "local_data_url"}),
                )
            except (OSError, requests.RequestException) as retry_exc:
                retry_error = sanitize_secret_error(str(retry_exc))
                return {
                    "ok": False,
                    "error": (
                        "AI MediaKit 图片翻译原图URL请求失败，原因疑似原图尺寸不支持；"
                        f"已改用本地压缩/缩放图重试仍失败：原图错误：{first_error}；重试错误：{retry_error}"
                    ),
                }
        else:
            return {"ok": False, "error": f"AI MediaKit 图片翻译请求失败：{first_error}"}

    image_payload = extract_image_from_aimediakit_response(payload)
    if not image_payload:
        return {"ok": False, "error": f"AI MediaKit 图片翻译未返回图片：{json.dumps(payload, ensure_ascii=False)[:400]}"}
    try:
        if image_payload.startswith("http://") or image_payload.startswith("https://"):
            translated_bytes = download_remote_image(image_payload)
        else:
            translated_bytes = base64.b64decode(image_payload.split(",", 1)[-1])
        translated = Image.open(BytesIO(translated_bytes)).convert("RGBA")
        save_standard_product_image(translated, output_path, role=role, quality=92)
        return {"ok": True, "editor": f"aimediakit_{payload.get('task_type') or 'translate'}"}
    except (OSError, ValueError, UnidentifiedImageError, requests.RequestException) as exc:
        return {"ok": False, "error": f"AI MediaKit 图片翻译返回图片无法识别：{exc}"}


def remove_image_elements_with_aimediakit(
    image: Image.Image,
    output_path: Path,
    role: str = "main",
    task_id: str = "",
    source_image_url: str = "",
) -> dict[str, Any]:
    config = get_default_model_config_for_translation()
    if not config or not config.api_key_encrypted:
        return {"ok": False, "error": "AI MediaKit 未配置。"}
    try:
        image_url = prepare_mediakit_image_url(image, task_id, output_path, "remove", source_image_url)
    except AutoPublishError as exc:
        return {"ok": False, "error": f"AI MediaKit 牛皮癣擦除输入图准备失败：{exc}"}
    try:
        payload = post_aimediakit_tool(
            AIMEDIAKIT_REMOVE_ELEMENTS_URL,
            config.api_key_encrypted,
            {"image_url": image_url},
            task_id=task_id,
            purpose="aimediakit_remove_image_elements",
            model=config.model_name or "AI MediaKit",
            meta=model_config_usage_meta(config),
        )
    except requests.RequestException as exc:
        first_error = sanitize_secret_error(str(exc))
        if source_image_url and should_retry_mediakit_with_local_image(first_error):
            try:
                payload = post_aimediakit_tool(
                    AIMEDIAKIT_REMOVE_ELEMENTS_URL,
                    config.api_key_encrypted,
                    {"image_url": image_url_for_mediakit(image, task_id, output_path, "remove_retry")},
                    task_id=task_id,
                    purpose="aimediakit_remove_image_elements",
                    model=config.model_name or "AI MediaKit",
                    meta=model_config_usage_meta(config, {"retry_input": "local_data_url"}),
                )
            except (OSError, requests.RequestException) as retry_exc:
                retry_error = sanitize_secret_error(str(retry_exc))
                return {
                    "ok": False,
                    "error": (
                        "AI MediaKit 牛皮癣擦除原图URL请求失败，原因疑似原图尺寸不支持；"
                        f"已改用本地压缩/缩放图重试仍失败：原图错误：{first_error}；重试错误：{retry_error}"
                    ),
                }
        else:
            return {"ok": False, "error": f"AI MediaKit 牛皮癣擦除请求失败：{first_error}"}
    image_payload = extract_image_from_aimediakit_response(payload)
    if not image_payload:
        return {"ok": False, "error": f"AI MediaKit 牛皮癣擦除未返回图片：{json.dumps(payload, ensure_ascii=False)[:400]}"}
    try:
        cleaned_bytes = download_remote_image(image_payload) if image_payload.startswith(("http://", "https://")) else base64.b64decode(image_payload.split(",", 1)[-1])
        cleaned = Image.open(BytesIO(cleaned_bytes)).convert("RGBA")
        save_standard_product_image(cleaned, output_path, role=role, quality=92)
        return {"ok": True, "editor": "aimediakit_remove_elements"}
    except (OSError, ValueError, UnidentifiedImageError, requests.RequestException) as exc:
        return {"ok": False, "error": f"AI MediaKit 牛皮癣擦除返回图片无法识别：{exc}"}


def post_aimediakit_tool(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    task_id: str = "",
    purpose: str = "aimediakit_tool",
    model: str = "AI MediaKit",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        status_code: int | None = None
        try:
            with AIMEDIAKIT_REQUEST_GATE:
                response = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=(12, 120),
                )
            status_code = response.status_code
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                if response.status_code >= 500 and attempt < 2:
                    last_error = requests.RequestException(f"HTTP {response.status_code} {response.text[:500]}")
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise requests.RequestException(f"HTTP {response.status_code} {response.text[:500]}") from exc
            try:
                data = response.json()
            except ValueError as exc:
                raise requests.RequestException(f"返回不是JSON：{response.text[:500]}") from exc
            if isinstance(data, dict) and data.get("error"):
                error_text = json.dumps(data, ensure_ascii=False)[:500]
                if attempt < 2:
                    last_error = requests.RequestException(error_text)
                    time.sleep(1.2 * (attempt + 1))
                    continue
                record_api_usage(
                    task_id,
                    provider="ai_mediakit",
                purpose=purpose,
                model=model,
                endpoint=endpoint,
                success=False,
                request_count=attempt + 1,
                image_count=1,
                status_code=status_code,
                error=error_text,
                    meta={**(meta or {}), "attempt": attempt + 1},
                )
                raise requests.RequestException(error_text)
            record_api_usage(
                task_id,
                provider="ai_mediakit",
                purpose=purpose,
                model=model,
                endpoint=endpoint,
                success=True,
                request_count=attempt + 1,
                image_count=1,
                status_code=status_code,
                meta={**(meta or {}), "attempt": attempt + 1},
            )
            return data if isinstance(data, dict) else {"data": data}
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= 2:
                for alt_config in get_model_configs_for_translation():
                    alt_key = str(alt_config.api_key_encrypted or "").strip()
                    if not alt_key or alt_key == api_key:
                        continue
                    alt_endpoint = AIMEDIAKIT_REMOVE_ELEMENTS_URL if "remove" in purpose else (alt_config.base_url or endpoint)
                    try:
                        with AIMEDIAKIT_REQUEST_GATE:
                            alt_response = requests.post(
                                alt_endpoint,
                                headers={"Authorization": f"Bearer {alt_key}", "Content-Type": "application/json"},
                                json=payload,
                                timeout=(20, 180),
                            )
                        alt_response.raise_for_status()
                        alt_data = alt_response.json()
                        if isinstance(alt_data, dict) and alt_data.get("error"):
                            raise requests.RequestException(json.dumps(alt_data, ensure_ascii=False)[:500])
                        record_api_usage(
                            task_id,
                            provider="ai_mediakit",
                            purpose=purpose,
                            model=alt_config.model_name or model,
                            endpoint=alt_endpoint,
                            success=True,
                            request_count=attempt + 2,
                            image_count=1,
                            status_code=alt_response.status_code,
                            meta=model_config_usage_meta(
                                alt_config,
                                {**{k: v for k, v in (meta or {}).items() if k != "key_label"}, "attempt": attempt + 1, "fallback": "key_pool"},
                            ),
                        )
                        return alt_data if isinstance(alt_data, dict) else {"data": alt_data}
                    except (requests.RequestException, ValueError) as alt_exc:
                        record_api_usage(
                            task_id,
                            provider="ai_mediakit",
                            purpose=purpose,
                            model=alt_config.model_name or model,
                            endpoint=alt_endpoint,
                            success=False,
                            request_count=1,
                            image_count=1,
                            error=str(alt_exc),
                            meta=model_config_usage_meta(
                                alt_config,
                                {**{k: v for k, v in (meta or {}).items() if k != "key_label"}, "fallback": "key_pool"},
                            ),
                        )
                        continue
                try:
                    with AIMEDIAKIT_REQUEST_GATE:
                        result = post_aimediakit_with_powershell(endpoint, api_key, payload, sanitize_secret_error(str(exc)))
                    record_api_usage(
                        task_id,
                        provider="ai_mediakit",
                        purpose=purpose,
                        model=model,
                        endpoint=endpoint,
                        success=True,
                        request_count=attempt + 2,
                        image_count=1,
                        status_code=status_code,
                        meta={**(meta or {}), "attempt": attempt + 1, "fallback": "powershell"},
                    )
                    return result
                except requests.RequestException as fallback_exc:
                    record_api_usage(
                        task_id,
                        provider="ai_mediakit",
                        purpose=purpose,
                        model=model,
                        endpoint=endpoint,
                        success=False,
                        request_count=attempt + 2,
                        image_count=1,
                        status_code=status_code,
                        error=str(fallback_exc),
                        meta={**(meta or {}), "attempt": attempt + 1, "fallback": "powershell"},
                    )
                    raise
            time.sleep(1.2 * (attempt + 1))
    raise requests.RequestException(str(last_error or "AI MediaKit 请求失败"))


def should_retry_mediakit_with_local_image(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    return "800013" in lowered or "resolution not supported" in lowered or "image resolution not supported" in lowered


def is_valid_mediakit_image_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith(("http://", "https://", "mediakit://", "tos://", "vod://"))


def mediakit_source_image_supported(image: Image.Image, action: str) -> bool:
    width, height = image.size
    if "remove" in action:
        return 128 <= width <= 2560 and 128 <= height <= 1440
    return width >= 10 and height >= 10 and width * height <= 20_000_000


def prepare_mediakit_image_url(image: Image.Image, task_id: str, output_path: Path, action: str, source_image_url: str = "") -> str:
    source = str(source_image_url or "").strip()
    if is_valid_mediakit_image_url(source) and mediakit_source_image_supported(image, action):
        return source
    return image_url_for_mediakit(image, task_id, output_path, action)


def image_url_for_mediakit(image: Image.Image, task_id: str, output_path: Path, action: str) -> str:
    _ensure_runtime_dir()
    safe_task_id = task_id or uuid4().hex
    temp_dir = RUNTIME_DIR / "mediakit_inputs" / safe_task_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{output_path.stem}_{action}_{uuid4().hex[:8]}.jpg"
    temp_path.write_bytes(image_translation_request_bytes(image, action=action))
    try:
        upload_images_to_ecs(safe_task_id, [temp_path])
        return f"{DEFAULT_ASSET_BASE_URL.rstrip('/')}/{safe_task_id}/{temp_path.name}"
    except Exception as exc:
        raise AutoPublishError(f"本地中间图上传公网失败，无法提交 AI MediaKit：{exc}") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def image_translation_request_bytes(image: Image.Image, action: str = "translate") -> bytes:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    max_width, max_height = (2560, 1440) if "remove" in action else (4096, 4096)
    ratio = min(max_width / max(prepared.width, 1), max_height / max(prepared.height, 1), 1.0)
    if ratio < 1:
        prepared = prepared.resize((max(32, int(prepared.width * ratio)), max(32, int(prepared.height * ratio))), Image.Resampling.LANCZOS)
    if "remove" not in action and prepared.width * prepared.height > 20_000_000:
        ratio = (20_000_000 / max(prepared.width * prepared.height, 1)) ** 0.5
        prepared = prepared.resize((max(32, int(prepared.width * ratio)), max(32, int(prepared.height * ratio))), Image.Resampling.LANCZOS)
    for quality in (90, 84, 78, 72):
        buffer = BytesIO()
        prepared.save(buffer, "JPEG", quality=quality, optimize=True)
        if buffer.tell() <= 4 * 1024 * 1024:
            return buffer.getvalue()
    raise OSError("图片压缩后仍超过图像翻译请求限制")


def extract_image_from_aimediakit_response(payload: Any) -> str:
    candidates: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
        elif isinstance(value, list):
            for item in value:
                visit(item, key)
        elif isinstance(value, str):
            lowered_key = key.lower()
            if value.startswith(("http://", "https://", "data:image/")):
                if any(token in lowered_key for token in ("image", "url", "result", "output", "file")):
                    candidates.append(value)
            elif len(value) > 200 and re.match(r"^[A-Za-z0-9+/=\s]+$", value):
                if any(token in lowered_key for token in ("image", "base64", "b64", "data")):
                    candidates.append(value.strip())

    visit(payload)
    return candidates[0] if candidates else ""


def download_remote_image(image_url: str) -> bytes:
    last_error = ""
    for attempt in range(3):
        try:
            response = requests.get(
                image_url,
                headers={"User-Agent": "Mozilla/5.0 TKAutoPublish/1.0", "Accept": "image/*,*/*;q=0.8"},
                timeout=(20, 90),
            )
            response.raise_for_status()
            if not response.content:
                raise requests.RequestException("empty image response")
            return response.content
        except requests.RequestException as exc:
            last_error = sanitize_secret_error(str(exc))
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
    return download_remote_image_with_powershell(image_url, last_error)


def sanitize_secret_error(value: str) -> str:
    value = re.sub(r"(client_secret=)[^&\\s]+", r"\1***", value or "")
    value = re.sub(r"(client_id=)[^&\\s]+", r"\1***", value)
    return value


def alicdn_image_url_candidates(image_url: str) -> list[str]:
    source = normalize_image_url(image_url)
    candidates = [source]
    if "cbu01.alicdn.com" in source:
        candidates.extend(source.replace("cbu01.alicdn.com", host) for host in ("cbu02.alicdn.com", "cbu03.alicdn.com"))
    elif "cbu02.alicdn.com" in source:
        candidates.append(source.replace("cbu02.alicdn.com", "cbu01.alicdn.com"))
    if source.startswith("https://") and "alicdn.com" in source:
        candidates.append("http://" + source[len("https://") :])
    return unique_urls(candidates)


def requires_ai_regeneration(analysis: dict[str, Any]) -> bool:
    text_regions = [item for item in (analysis.get("text_regions") or []) if isinstance(item, dict)]
    remove_regions = [item for item in (analysis.get("remove_regions") or []) if isinstance(item, dict)]
    if text_regions:
        return True
    risky_tokens = ("face", "人脸", "人物", "真人", "logo", "品牌", "watermark", "水印", "qr", "二维码", "contact", "联系方式", "ip")
    for item in remove_regions:
        reason = str(item.get("reason") or "").lower()
        if any(token in reason for token in risky_tokens):
            return True
    return False


def process_image_low_cost(
    image: Image.Image,
    output_path: Path,
    product: dict[str, Any],
    role: str = "main",
    sku_text: str = "",
    target_language: str = "ja",
    task_id: str = "",
    source_image_url: str = "",
) -> dict[str, Any]:
    analysis = analyze_image_low_cost(image, product, task_id=task_id)
    if role in {"main", "sku"}:
        remove_result = remove_image_elements_with_aimediakit(image, output_path, role=role, task_id=task_id, source_image_url=source_image_url)
        if remove_result.get("ok"):
            return {"keep": True, "analysis": analysis, "editor": "aimediakit_remove_elements"}
        raise AutoPublishError(
            f"{role_image_label(role)}必须擦除品牌/中文/Logo/水印/二维码/联系方式等风险元素，但 AI MediaKit 牛皮癣擦除失败。{remove_result.get('error') or ''}"
        )
    if analysis.get("keep") is False and role == "detail":
        delete_reason = deletion_reason_if_factory_or_pure_text(analysis)
        if delete_reason:
            return {"keep": False, "reason": delete_reason, "analysis": analysis, "editor": "promo_filter"}
    if role == "detail" and has_blocking_visual_risk(analysis):
        remove_result = remove_image_elements_with_aimediakit(image, output_path, role=role, task_id=task_id, source_image_url=source_image_url)
        if not remove_result.get("ok"):
            raise AutoPublishError(f"详情图含Logo、水印、二维码或联系方式等风险元素，AI MediaKit 牛皮癣擦除失败。{remove_result.get('error') or ''}")
        reject_reason = reject_processed_detail_if_invalid(output_path, product, task_id=task_id)
        if reject_reason:
            return {"keep": False, "reason": reject_reason, "analysis": analysis, "editor": "discarded_after_remove"}
        if detail_image_needs_translation(analysis):
            try:
                cleaned_image = Image.open(output_path).convert("RGBA")
            except (OSError, UnidentifiedImageError) as exc:
                raise AutoPublishError(f"详情图风险元素擦除后本地图片无法读取。{exc}") from exc
            translation_result = translate_detail_image_with_aimediakit(
                cleaned_image,
                output_path,
                role=role,
                target_language=target_language,
                task_id=task_id,
                source_image_url="",
                analysis=analysis,
            )
            if translation_result.get("ok"):
                translated_reject_reason = reject_processed_detail_if_invalid(output_path, product, task_id=task_id)
                if translated_reject_reason:
                    return {
                        "keep": False,
                        "reason": translated_reject_reason,
                        "analysis": analysis,
                        "editor": "discarded_after_translate",
                    }
                return {"keep": True, "analysis": analysis, "editor": "aimediakit_remove_then_translate"}
            raise AutoPublishError(
                f"详情图风险文字已擦除，但普通中文/英文说明日语翻译失败。{translation_result.get('error') or ''}"
            )
        return {"keep": True, "analysis": analysis, "editor": "aimediakit_remove_elements"}
    if role == "detail" and detail_image_needs_translation(analysis):
        translation_result = translate_detail_image_with_aimediakit(
            image,
            output_path,
            role=role,
            target_language=target_language,
            task_id=task_id,
            source_image_url=source_image_url,
            analysis=analysis,
        )
        if translation_result.get("ok"):
            translated_reject_reason = reject_processed_detail_if_invalid(output_path, product, task_id=task_id)
            if translated_reject_reason:
                return {
                    "keep": False,
                    "reason": translated_reject_reason,
                    "analysis": analysis,
                    "editor": "discarded_after_translate",
                }
            return {"keep": True, "analysis": analysis, "editor": "aimediakit_translate"}
        raise AutoPublishError(f"详情图含普通中文/英文说明文字，AI MediaKit 日语翻译失败。{translation_result.get('error') or ''}")
    save_standard_product_image(image, output_path, role=role, quality=90)
    return {"keep": True, "analysis": analysis, "editor": "original_clean"}


def reject_processed_detail_if_invalid(output_path: Path, product: dict[str, Any], task_id: str = "") -> str:
    try:
        processed = Image.open(output_path).convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        return f"处理后的详情图无法读取：{exc}"
    if is_blank_or_frame_only_image(processed):
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return "处理后的详情图无商品主体，仅剩空白/黑框/装饰边框，已删除。"
    reason = detect_supply_chain_promo_image(processed, product, task_id=task_id)
    if reason:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return reason
    return ""


def is_blank_or_frame_only_image(image: Image.Image) -> bool:
    sample = ImageOps.exif_transpose(image).convert("RGB")
    sample.thumbnail((360, 360), Image.Resampling.LANCZOS)
    pixels = list(sample.getdata())
    if not pixels:
        return True
    total = len(pixels)
    white_like = 0
    black_like = 0
    saturated = 0
    mid_detail = 0
    for red, green, blue in pixels:
        max_c = max(red, green, blue)
        min_c = min(red, green, blue)
        if max_c > 238 and min_c > 220:
            white_like += 1
        if max_c < 36:
            black_like += 1
        if max_c - min_c > 28:
            saturated += 1
        if 45 <= max_c <= 220 and max_c - min_c > 12:
            mid_detail += 1
    white_ratio = white_like / total
    black_ratio = black_like / total
    saturated_ratio = saturated / total
    mid_detail_ratio = mid_detail / total
    return (white_ratio + black_ratio > 0.82 and saturated_ratio < 0.035 and mid_detail_ratio < 0.08)


def deletion_reason_if_factory_or_pure_text(analysis: dict[str, Any]) -> str:
    reason = clean_html_text(str(analysis.get("reason") or ""))
    lowered = reason.lower()
    factory_tokens = (
        "工厂",
        "厂家",
        "源头",
        "车间",
        "仓库",
        "批发",
        "一件代发",
        "招商",
        "代理",
        "供应链",
        "客服",
        "联系方式",
        "二维码",
        "运费",
        "物流",
        "售后",
        "factory",
        "wholesale",
        "supplier",
        "customer service",
        "shipping",
    )
    pure_text_tokens = ("纯文字", "只有文字", "无商品主体", "没有商品主体", "不包含商品主体", "文字说明图", "pure text", "text only")
    if any(token in reason for token in factory_tokens) or any(token in lowered for token in factory_tokens):
        return f"工厂/供应链宣传图：{reason or '命中工厂或供应链宣传内容'}"
    if any(token in reason for token in pure_text_tokens) or any(token in lowered for token in pure_text_tokens):
        return f"纯文字图片：{reason or '画面主要为文字且无商品主体'}"
    return ""


def repair_processed_image_artifacts(output_path: Path, role: str) -> str:
    try:
        processed = Image.open(output_path).convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        return f"处理后的{role_image_label(role)}无法读取：{exc}"
    blocks = find_large_dark_blocks(processed)
    if not blocks:
        return ""
    media_result = remove_image_elements_with_aimediakit(processed, output_path, role=role, task_id="artifact_repair", source_image_url="")
    if media_result.get("ok"):
        try:
            media_checked = Image.open(output_path).convert("RGBA")
        except (OSError, UnidentifiedImageError) as exc:
            return f"MediaKit 二次擦除黑色/灰色遮挡块后图片无法读取：{exc}"
        if not find_large_dark_blocks(media_checked):
            return ""
    repaired = repair_dark_blocks(processed, blocks)
    save_standard_product_image(repaired, output_path, role=role, quality=92)
    try:
        checked = Image.open(output_path).convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        return f"黑色/深色模糊遮挡块修复后图片无法读取：{exc}"
    remaining = find_large_dark_blocks(checked)
    if remaining:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        block = remaining[0]
        return (
            "AI MediaKit 处理后出现大面积黑色/灰色/半透明模糊遮挡块，已尝试 MediaKit 二次擦除和本地补背景但仍残留，"
            f"位置约 x={block['x']}%, y={block['y']}%, 宽={block['w']}%, 高={block['h']}%。"
        )
    return ""


def processed_image_artifact_reason(image: Image.Image) -> str:
    dark_blocks = find_large_dark_blocks(image)
    if dark_blocks:
        block = dark_blocks[0]
        return (
            "AI MediaKit 处理后出现大面积黑色/灰色/半透明模糊遮挡块，"
            f"疑似翻译或擦除残留补丁，位置约 x={block['x']}%, y={block['y']}%, "
            f"宽={block['w']}%, 高={block['h']}%。"
        )
    return ""


def repair_dark_blocks(image: Image.Image, blocks: list[dict[str, int]]) -> Image.Image:
    result = image.convert("RGBA")
    width, height = result.size
    for block in blocks:
        x1 = max(0, int(width * block["x"] / 100) - max(8, width // 80))
        y1 = max(0, int(height * block["y"] / 100) - max(8, height // 80))
        x2 = min(width, int(width * (block["x"] + block["w"]) / 100) + max(8, width // 80))
        y2 = min(height, int(height * (block["y"] + block["h"]) / 100) + max(8, height // 80))
        if x2 <= x1 or y2 <= y1:
            continue
        fill = surrounding_average_color(result, (x1, y1, x2, y2))
        patch = Image.new("RGBA", (x2 - x1, y2 - y1), fill)
        patch = patch.filter(ImageFilter.GaussianBlur(radius=max(2, min(patch.size) // 16)))
        mask = Image.new("L", patch.size, 230)
        feather = max(4, min(patch.size) // 10)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
        result.paste(patch, (x1, y1), mask)
    return result


def surrounding_average_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = image.size
    pad = max(8, min(width, height) // 80)
    outer = (max(0, x1 - pad), max(0, y1 - pad), min(width, x2 + pad), min(height, y2 + pad))
    pixels = image.convert("RGBA").load()
    bright_background_samples: list[tuple[int, int, int, int]] = []
    fallback_samples: list[tuple[int, int, int, int]] = []
    for y in range(outer[1], outer[3], max(1, (outer[3] - outer[1]) // 80 or 1)):
        for x in range(outer[0], outer[2], max(1, (outer[2] - outer[0]) // 80 or 1)):
            if x1 <= x < x2 and y1 <= y < y2:
                continue
            red, green, blue, alpha = pixels[x, y]
            if alpha < 16:
                continue
            brightness = (red + green + blue) / 3
            spread = max(red, green, blue) - min(red, green, blue)
            if brightness > 205 and spread < 45:
                bright_background_samples.append((red, green, blue, alpha))
                continue
            if brightness < 80:
                continue
            fallback_samples.append((red, green, blue, alpha))
    samples = bright_background_samples if len(bright_background_samples) >= 20 else fallback_samples
    if not samples:
        return (245, 245, 245, 255)
    red = sum(item[0] for item in samples) // len(samples)
    green = sum(item[1] for item in samples) // len(samples)
    blue = sum(item[2] for item in samples) // len(samples)
    alpha = sum(item[3] for item in samples) // len(samples)
    return (red, green, blue, alpha)


def find_large_dark_blocks(image: Image.Image) -> list[dict[str, int]]:
    sample = ImageOps.exif_transpose(image).convert("RGB")
    sample.thumbnail((180, 180), Image.Resampling.BILINEAR)
    width, height = sample.size
    if width <= 0 or height <= 0:
        return []
    pixels = sample.load()
    mask: list[list[bool]] = []
    for y in range(height):
        row: list[bool] = []
        for x in range(width):
            red, green, blue = pixels[x, y]
            brightness = (red + green + blue) / 3
            spread = max(red, green, blue) - min(red, green, blue)
            is_dark_patch = brightness < 58 and spread < 38
            is_gray_overlay = 45 < brightness < 190 and spread < 70
            row.append(is_dark_patch or is_gray_overlay)
        mask.append(row)

    visited = [[False] * width for _ in range(height)]
    blocks: list[dict[str, int]] = []
    total = width * height
    for start_y in range(height):
        for start_x in range(width):
            if visited[start_y][start_x] or not mask[start_y][start_x]:
                continue
            stack = [(start_x, start_y)]
            visited[start_y][start_x] = True
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y
            while stack:
                x, y = stack.pop()
                count += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height and not visited[ny][nx] and mask[ny][nx]:
                        visited[ny][nx] = True
                        stack.append((nx, ny))
            block_w = max_x - min_x + 1
            block_h = max_y - min_y + 1
            area_ratio = count / total
            if area_ratio >= 0.018 and block_w >= width * 0.12 and block_h >= height * 0.06:
                blocks.append(
                    {
                        "x": round(min_x / width * 100),
                        "y": round(min_y / height * 100),
                        "w": round(block_w / width * 100),
                        "h": round(block_h / height * 100),
                        "area": round(area_ratio * 100),
                    }
                )
    return sorted(blocks, key=lambda item: item["area"], reverse=True)


def analyze_image_low_cost(image: Image.Image, product: dict[str, Any], task_id: str = "") -> dict[str, Any]:
    config = get_default_model_config_for_images()
    if not config:
        return {"keep": True, "has_cjk_text": True, "risk": False, "reason": "视觉模型未配置，保守走 AI MediaKit 图片翻译。"}
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=560)).decode("ascii")
    instruction = (
        "快速判断1688商品图，低成本输出JSON。"
        "字段：keep=false 只允许用于工厂/供应链宣传图或纯文字无商品主体图；其他图片不要判删除。"
        "详情图里的尺寸图、功能说明图、参数/卖点图，即使商品主体不明显，也不要删除，普通中文/英文说明文字要标记供后续翻译成日语，不要当作风险擦除；"
        "只有整张图主要是工厂、批发、物流、客服、联系方式、二维码、店铺宣传，或纯文字公告且无商品主体时，keep=false；"
        "如果详情图清楚包含商品实物主体，必须 keep=true，并标记文字供后续翻译；"
        "如果是主图或SKU图，只要画面有任何中文/英文/数字说明、卖点文字、价格、参数、贴纸角标，has_any_text=true，后续必须擦除；"
        "任何图片中出现品牌名、商标Logo、BENNUO/冷刃/COLD、运输/运费/物流/配送/送料、退货/换货/返金/售后/保证/服务/再販売、联系方式、二维码、水印等不利于展示商品或违规风险内容，必须 risk=true 并写入 remove_regions，后续擦除，不要翻译保留；"
        "has_cjk_text=画面是否有中文汉字；"
        "has_latin_text=画面是否有英文或拉丁字母说明文字；"
        "has_any_text=画面是否有任何文字、数字说明、价格、参数、贴纸角标或营销标签；"
        "has_dense_text=画面是否为多段说明、参数表、规格表、尺寸图、密集卖点文字；"
        "risk=是否有人脸、品牌Logo、水印、二维码、联系方式、运输售后文字、明显侵权IP或平台标识；"
        "reason=简短原因。"
        "不要翻译，不要输出长文本。"
        f"商品标题：{clean_html_text(str(product.get('title') or ''))}。"
    )
    payload = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": "你是电商图片快速质检器，只输出JSON。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": 180,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        response_payload = response.json()
        usage = usage_from_response_payload(response_payload)
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="image_low_cost_analysis",
            model=config.model_name or "",
            endpoint=endpoint,
            success=True,
            image_count=1,
            status_code=response.status_code,
            meta=model_config_usage_meta(config),
            **usage,
        )
        content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", str(content), re.DOTALL)
        parsed = json.loads(match.group(0) if match else str(content))
        if not isinstance(parsed, dict):
            return {}
        return normalize_low_cost_analysis(parsed)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="image_low_cost_analysis",
            model=config.model_name or "",
            endpoint=endpoint,
            success=False,
            image_count=1,
            error=str(exc),
            meta=model_config_usage_meta(config),
        )
        return {"keep": True, "has_cjk_text": True, "risk": False, "reason": "快速图片判断失败，保守走 AI MediaKit 图片翻译。"}


def normalize_low_cost_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(parsed)
    has_cjk = bool(analysis.get("has_cjk_text") or analysis.get("has_chinese") or analysis.get("contains_chinese"))
    has_latin = bool(analysis.get("has_latin_text") or analysis.get("has_english") or analysis.get("contains_english"))
    risk = bool(analysis.get("risk") or analysis.get("has_risk"))
    analysis["has_dense_text"] = bool(analysis.get("has_dense_text") or analysis.get("dense_text") or analysis.get("is_dense_text"))
    if has_cjk or has_latin:
        source_text = "中文/英文" if has_cjk and has_latin else ("中文" if has_cjk else "英文")
        analysis["text_regions"] = [{"source_text": source_text}]
    else:
        analysis["text_regions"] = []
    analysis["has_latin_text"] = has_latin
    if risk:
        analysis["remove_regions"] = [{"reason": clean_html_text(str(analysis.get("reason") or "risk"))}]
    else:
        analysis["remove_regions"] = []
    analysis["keep"] = bool(analysis.get("keep", True))
    return analysis


def analysis_has_cjk_text(analysis: dict[str, Any]) -> bool:
    if analysis.get("has_cjk_text") is True or analysis.get("contains_cjk") is True:
        return True
    for item in (analysis.get("text_regions") or []):
        if not isinstance(item, dict):
            continue
        text = clean_html_text(str(item.get("source_text") or ""))
        if contains_cjk(text):
            return True
    return False


def analysis_has_latin_text(analysis: dict[str, Any]) -> bool:
    if analysis.get("has_latin_text") is True or analysis.get("has_english") is True or analysis.get("contains_english") is True:
        return True
    for item in (analysis.get("text_regions") or []):
        if not isinstance(item, dict):
            continue
        text = clean_html_text(str(item.get("source_text") or ""))
        if re.search(r"[A-Za-z]", text):
            return True
    return False


def detail_image_needs_translation(analysis: dict[str, Any]) -> bool:
    return analysis_has_cjk_text(analysis) or analysis_has_latin_text(analysis)


def analysis_has_any_text(analysis: dict[str, Any]) -> bool:
    if analysis.get("has_any_text") is True or analysis.get("has_text") is True:
        return True
    return bool(analysis.get("text_regions") or analysis.get("text") or analysis.get("texts"))


def has_blocking_visual_risk(analysis: dict[str, Any]) -> bool:
    risky_tokens = (
        "face",
        "person",
        "model",
        "人脸",
        "人物",
        "真人",
        "模特",
        "logo",
        "品牌",
        "品牌名",
        "商标",
        "watermark",
        "水印",
        "qr",
        "二维码",
        "contact",
        "联系方式",
        "店铺",
        "平台标识",
        "运输",
        "运费",
        "物流",
        "配送",
        "送料",
        "退货",
        "返品",
        "交換",
        "返金",
        "售后",
        "保証",
        "服务",
        "サービス",
        "再販売",
        "再贩卖",
        "bennuo",
        "cold",
        "ip",
        "侵权",
    )
    reason_text = str(analysis.get("reason") or "").lower()
    if (analysis.get("risk") is True or analysis.get("has_risk") is True) and any(token in reason_text for token in risky_tokens):
        return True
    for item in (analysis.get("remove_regions") or []):
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").lower()
        if any(token in reason for token in risky_tokens):
            return True
    return False


def likely_contains_product(image: Image.Image) -> bool:
    width, height = image.size
    if width < 320 or height < 320:
        return False
    ratio = width / max(height, 1)
    return 0.25 <= ratio <= 4


def detect_supply_chain_promo_image(image: Image.Image, product: dict[str, Any], task_id: str = "") -> str:
    config = get_default_model_config_for_images()
    if not config:
        return ""
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=560)).decode("ascii")
    instruction = (
        "判断这张1688商品详情图片是否属于应直接删除的无效详情图。"
        "delete=true 只允许两类："
        "1）工厂/供应链/店铺宣传图：一件代发、厂家实力、源头工厂、工厂介绍、厂房、生产车间、流水线、仓库、"
        "团队合影、企业资质、招商加盟、代理招募、批发政策、发货流程、售后承诺、店铺宣传、联系方式、二维码、"
        "运费说明、物流说明、客服说明、长期合作、价格咨询、工厂价格、卸売、送料、請求書、カスタマーサービス；"
        "2）纯文字图片：画面主要是文字公告/说明，且没有商品主体。"
        "不要因为尺寸图、功能说明图、参数/卖点图就删除；这些图应保留并交给后续翻译。"
        "只擦除风险元素和翻译文字，删除图片只能用于工厂/供应链宣传或纯文字无商品主体图。"
        f"商品标题：{clean_html_text(str(product.get('title') or ''))}。"
        '只返回JSON：{"delete":true或false,"reason":"简短原因"}'
    )
    payload = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": "你是电商商品图片快速分类器，只输出JSON。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": 120,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=25,
        )
        response.raise_for_status()
        response_payload = response.json()
        usage = usage_from_response_payload(response_payload)
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="detail_prefilter_analysis",
            model=config.model_name or "",
            endpoint=endpoint,
            success=True,
            image_count=1,
            status_code=response.status_code,
            meta=model_config_usage_meta(config),
            **usage,
        )
        content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", str(content), re.DOTALL)
        parsed = json.loads(match.group(0) if match else str(content))
        if isinstance(parsed, dict) and parsed.get("delete") is True:
            reason = clean_html_text(str(parsed.get("reason") or "无效详情图"))
            return f"已跳过无效详情图：{reason}"
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="detail_prefilter_analysis",
            model=config.model_name or "",
            endpoint=endpoint,
            success=False,
            image_count=1,
            error=str(exc),
            meta=model_config_usage_meta(config),
        )
        return ""
    return ""


def analyze_image_compliance(image: Image.Image, product: dict[str, Any]) -> dict[str, Any]:
    config = get_default_model_config_for_images()
    if not config:
        return {}
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=900)).decode("ascii")
    instruction = {
        "product_title": product.get("title", ""),
        "requirements": [
            "keep=false 只允许用于工厂/供应链宣传图或纯文字无商品主体图；其他情况不要删除图片",
            "识别图片中的中文文字区域，并翻译为自然日语",
            "详情图如果只是尺寸图、功能说明图、参数/卖点图，不要删除，应保留并交给后续翻译。",
            "详情图即使只有日文文字，也只有在属于工厂/供应链宣传或纯文字无商品主体图时才能 keep=false。",
            "详情图如果清楚包含商品实物主体，即使有尺寸/功能说明文字，也 keep=true，并翻译文字。",
            "纯店铺广告、工厂/供应链宣传、二维码/联系方式占主导、纯文字公告无商品主体时 keep=false；人物或明显侵权IP占主导时标记 remove_regions 交给擦除，不要直接删除。",
            "识别需要抹除的侵权/风险信息：Logo、品牌、商标、BENNUO、冷刃、COLD、二维码、联系方式、水印、店铺名、平台标识、动漫/IP、人物脸部、运输/运费/物流/配送/送料、退货/换货/返金/售后/保证/服务/再販売等文字",
            "输出 JSON，不要解释",
        ],
        "schema": {
            "keep": True,
            "reason": "",
            "text_regions": [{"box": [0, 0, 100, 40], "source_text": "中文", "japanese_text": "日本語"}],
            "remove_regions": [{"box": [0, 0, 100, 40], "reason": "logo/watermark/ip/qr/contact/face"}],
        },
        "box_rule": "box 为原图像素坐标 [x,y,width,height]，无法确定区域时返回空数组。",
    }
    payload = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": "你是商品图片合规审核和日本本地化助手。只输出合法 JSON。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": json.dumps(instruction, ensure_ascii=False)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        return parsed if isinstance(parsed, dict) else {}
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return {}


def translate_analysis_text_regions(analysis: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    regions = [item for item in (analysis.get("text_regions") or []) if isinstance(item, dict)]
    source_texts = [clean_html_text(str(item.get("source_text") or "")) for item in regions]
    source_texts = [text for text in source_texts if text and contains_cjk(text)]
    if not source_texts:
        return analysis
    config = get_default_model_config_for_translation()
    if not config or not config.api_key_encrypted or not config.base_url or not config.model_name:
        return analysis
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    payload = {
        "model": config.model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "あなたは日本向けEC商品画像の短文翻訳者です。JSONのみ出力してください。"
                    "中国語の画像内テキストを、自然で短く読みやすい日本語に翻訳します。"
                    "誇大表現、配送日数、ブランド/IP/特許/公式表現、1688/阿里巴巴/卸売/メーカー等の供給側表現は禁止。"
                    "画像内に収まるよう長すぎる訳を避け、意味を保った短い表現にしてください。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "product_title": product.get("title") or "",
                        "texts": source_texts,
                        "output_schema": {"translations": [{"source": "原文", "ja": "自然な短い日本語"}]},
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return analysis
    translations: dict[str, str] = {}
    for item in parsed.get("translations", []) if isinstance(parsed, dict) else []:
        if not isinstance(item, dict):
            continue
        source = clean_html_text(str(item.get("source") or ""))
        japanese = sanitize_image_label(str(item.get("ja") or item.get("japanese") or ""))
        if source and japanese:
            translations[source] = japanese
    if not translations:
        return analysis
    updated = dict(analysis)
    updated_regions: list[dict[str, Any]] = []
    for item in regions:
        region = dict(item)
        source = clean_html_text(str(region.get("source_text") or ""))
        if source in translations:
            region["japanese_text"] = translations[source]
        updated_regions.append(region)
    updated["text_regions"] = updated_regions
    return updated


def get_default_model_config_for_translation() -> ModelConfig | None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        configs = get_model_configs_for_translation(db)
        return pick_from_pool("aimediakit", configs) if configs else None
    finally:
        db.close()


def get_model_configs_for_translation(db: Session | None = None) -> list[ModelConfig]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        configs = [
            item
            for item in select_auto_publish_model_configs(db, "image_text_translation")
            if item.api_key_encrypted and is_translation_model(item)
        ]
        third_parties = db.scalars(
            select(ThirdPartyConfig)
            .where(
                ThirdPartyConfig.service_type.in_(
                    (
                        "aimediakit",
                        "ai_mediakit",
                        "volcengine_mediakit",
                        "volcengine-mediakit",
                        "mediakit",
                        "doubao_seed_translation",
                        "seed_translation",
                    )
                ),
                ThirdPartyConfig.status == 1,
            )
            .order_by(ThirdPartyConfig.id.desc())
        ).all()
        for third_party in third_parties:
            api_key = str(third_party.access_key_encrypted or third_party.secret_key_encrypted or "").strip()
            if not api_key:
                continue
            configs.append(
                ModelConfig(
                    id=-(third_party.id or 0),
                    config_name=third_party.config_name or "AI MediaKit",
                    provider=third_party.service_type or "ai_mediakit",
                    model_type="image_text_translation",
                    base_url=third_party.api_base_url or AIMEDIAKIT_IMAGE_TRANSLATE_URL,
                    api_key_encrypted=api_key,
                    model_name="AI MediaKit",
                    status=1,
                    remark=third_party.remark or "auto_publish:image_text_translation",
                )
            )
        return dedupe_model_config_pool(configs)
    finally:
        if close_db:
            db.close()


def get_default_model_config_for_images() -> ModelConfig | None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        configs = select_auto_publish_model_configs(db, "image_analysis")
        return pick_from_pool("doubao_image_analysis", configs) if configs else None
    finally:
        db.close()


def get_default_model_config_for_image_generation() -> ModelConfig | None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return select_auto_publish_model_config(db, "image_generation")
    finally:
        db.close()


def get_model_configs_for_image_generation() -> list[ModelConfig]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        configs = db.scalars(
            select(ModelConfig).where(ModelConfig.status == 1).order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
        ).all()
        preferred = sort_by_model_priority(
            [item for item in configs if is_seedream_model(item)],
            DOUBAO_IMAGE_ENDPOINTS + DOUBAO_IMAGE_MODELS,
        )
        return [item for item in preferred if item.api_key_encrypted and item.base_url and item.model_name]
    finally:
        db.close()


def edit_image_with_seedream(
    image: Image.Image,
    output_path: Path,
    product: dict[str, Any],
    analysis: dict[str, Any],
    role: str = "main",
    sku_text: str = "",
    label_variant: int = 1,
    fast_clean: bool = False,
) -> dict[str, Any]:
    text_regions = [item for item in (analysis.get("text_regions") or []) if isinstance(item, dict)]
    remove_regions = [item for item in (analysis.get("remove_regions") or []) if isinstance(item, dict)]
    configs = get_model_configs_for_image_generation()
    if not configs:
        return {"ok": False}

    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=1536)).decode("ascii")
    errors: list[str] = []
    if fast_clean:
        configs = configs[:1]
    for config in configs:
        endpoint = image_generation_endpoint(config)
        prompt = (
            build_fast_clean_image_prompt(product, role=role, sku_text=sku_text)
            if fast_clean
            else build_seedream_image_edit_prompt(product, analysis, config, role=role, sku_text=sku_text)
        )
        if fast_clean:
            negative_prompt = (
                "商品主体不一致、商品结构变形、颜色不一致、材质不一致、SKU不一致、用途不一致、"
                "任何文字、中文、日语、英文、数字说明、标题、广告语、价格、参数、促销标签、贴纸、"
                "品牌logo、水印、二维码、联系方式、平台标识、人物、人脸、手、手臂、身体、模特、动物、"
                "动漫IP、侵权元素、新增物体、商品缺失、背景破损、白块补丁、色块、马赛克、拼贴、纯白抠图、模糊、低清晰度"
            )
        elif role == "detail":
            negative_prompt = (
                "商品主体不一致、商品结构变形、颜色不一致、规格不一致、用途不一致、低清晰度、模糊、廉价海报、"
                "白块补丁、色块遮挡、马赛克遮挡、文字贴片、大块文字面板、文字遮挡商品、随机文字、无意义日语、背景无关文字、窗户文字、墙面文字、衣服文字、残留中文、乱码、1688、阿里巴巴、厂家、批发、"
                "水印、品牌logo、二维码、联系方式、保留原真人脸、漫画脸、卡通脸、遮挡脸、面部马赛克、动漫IP、侵权元素、纯白底、白底抠图、模糊日语、乱码日语、"
                "断手、断臂、残肢、畸形手指、多手、多余手臂、手从商品里穿出、佩戴方式不合理、使用方式不合理、人体结构错误、物理关系错误"
            )
        else:
            negative_prompt = (
                "商品主体不一致、商品结构变形、颜色不一致、规格不一致、用途不一致、低清晰度、模糊、廉价海报、"
                "白块补丁、色块遮挡、马赛克遮挡、文字贴片、大块文字面板、文字遮挡商品、随机文字、无意义日语、背景文字、窗户文字、墙面文字、衣服文字、残留中文、乱码、1688、阿里巴巴、厂家、批发、"
                "水印、品牌logo、二维码、联系方式、保留原真人脸、漫画脸、卡通脸、遮挡脸、面部马赛克、动漫IP、侵权元素、纯白底、白底抠图、任何文字、"
                "断手、断臂、残肢、畸形手指、多手、多余手臂、手从商品里穿出、佩戴方式不合理、使用方式不合理、人体结构错误、物理关系错误"
            )
        payload: dict[str, Any] = {
            "model": config.model_name,
            "prompt": prompt,
            "image": data_url,
            "response_format": "b64_json",
            "size": SEEDREAM_REQUEST_SIZE,
            "watermark": False,
            "negative_prompt": negative_prompt,
            "denoising_strength": 0.24 if fast_clean else (0.34 if role == "main" else 0.3),
        }
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
                json=payload,
                timeout=min(AI_IMAGE_TIMEOUT_SECONDS, 55) if fast_clean else AI_IMAGE_TIMEOUT_SECONDS,
            )
            if response.status_code >= 400 and "denoising_strength" in payload:
                payload.pop("denoising_strength", None)
                payload.pop("size", None)
                response = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=min(AI_IMAGE_TIMEOUT_SECONDS, 55) if fast_clean else AI_IMAGE_TIMEOUT_SECONDS,
                )
            if response.status_code >= 400:
                errors.append(f"{config.model_name}: {response_error_message(response)}")
                continue
            edited = image_from_generation_response(response.json())
            if not edited:
                errors.append(f"{config.model_name}: Seedream 未返回图片。")
                continue
            save_standard_product_image(edited, output_path, role=role, quality=94)
            return {"ok": True, "model": config.model_name}
        except (requests.RequestException, OSError, ValueError) as exc:
            errors.append(f"{config.model_name}: {exc}")
    return {"ok": False, "error": "Seedream 图片改写失败：" + "；".join(errors[-3:])}


def generate_reference_image(
    reference_path: Path,
    output_path: Path,
    product: dict[str, Any],
    role: str,
    index: int,
    sku_text: str = "",
) -> bool:
    configs = get_model_configs_for_image_generation()
    if not configs:
        return False
    try:
        reference = Image.open(reference_path)
        reference = ImageOps.exif_transpose(reference).convert("RGB")
    except (OSError, UnidentifiedImageError):
        return False
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(reference, max_size=1536)).decode("ascii")
    for config in configs:
        endpoint = image_generation_endpoint(config)
        prompt = build_seedream_generation_prompt(product, role=role, index=index, sku_text=sku_text)
        payload: dict[str, Any] = {
            "model": config.model_name,
            "prompt": prompt,
            "image": data_url,
            "response_format": "b64_json",
            "size": SEEDREAM_REQUEST_SIZE,
            "watermark": False,
            "negative_prompt": (
                "商品不一致、颜色不一致、结构变形、规格不一致、用途不一致、增加无关物体、品牌logo、中文、"
                "1688、阿里巴巴、厂家、批发、二维码、联系方式、水印、保留原真人脸、漫画脸、卡通脸、遮挡脸、面部马赛克、动漫IP、低清晰度、模糊、"
                "廉价海报、大块文字、随机文字、无意义日语、背景文字、窗户文字、墙面文字、衣服文字、白色说明框、色块遮挡、马赛克遮挡、文字遮挡商品、纯白底、白底抠图、模糊日语、乱码日语、"
                "断手、断臂、残肢、畸形手指、多手、多余手臂、突然出现的手、手从商品里穿出、佩戴方式不合理、使用方式不合理、人体结构错误、物理关系错误"
            ),
            "denoising_strength": 0.38 if role == "main" else 0.32,
        }
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
                json=payload,
                timeout=AI_IMAGE_TIMEOUT_SECONDS,
            )
            if response.status_code >= 400 and "denoising_strength" in payload:
                payload.pop("denoising_strength", None)
                payload.pop("size", None)
                response = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=AI_IMAGE_TIMEOUT_SECONDS,
                )
            if response.status_code >= 400:
                continue
            generated = image_from_generation_response(response.json())
            if not generated:
                continue
            save_standard_product_image(generated, output_path, role=role, quality=94)
            return True
        except (requests.RequestException, OSError, ValueError):
            continue
    return False


def quick_reference_image(
    reference_path: Path,
    output_path: Path,
    product: dict[str, Any],
    role: str,
    index: int,
    sku_text: str = "",
) -> bool:
    try:
        reference = Image.open(reference_path)
        reference = ImageOps.exif_transpose(reference).convert("RGBA")
    except (OSError, UnidentifiedImageError):
        return False
    width, height = reference.size
    crop_variants = (
        (0.0, 0.0, 1.0, 1.0),
        (0.03, 0.02, 0.97, 0.98),
        (0.0, 0.04, 0.96, 1.0),
        (0.04, 0.0, 1.0, 0.96),
        (0.02, 0.02, 0.98, 0.98),
    )
    left_r, top_r, right_r, bottom_r = crop_variants[(max(index, 1) - 1) % len(crop_variants)]
    cropped = reference.crop(
        (
            int(width * left_r),
            int(height * top_r),
            max(int(width * right_r), 1),
            max(int(height * bottom_r), 1),
        )
    )
    image = ImageEnhance.Sharpness(cropped).enhance(1.08)
    image = ImageEnhance.Contrast(image).enhance(1.03)
    image = ImageEnhance.Color(image).enhance(1.02)
    save_standard_product_image(image, output_path, role=role, quality=90)
    return True


def image_generation_endpoint(config: ModelConfig) -> str:
    endpoint = config.base_url.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint.endswith("/images/generations"):
        endpoint = f"{endpoint}/images/generations"
    return endpoint


def response_error_message(response: requests.Response) -> str:
    text = response.text.strip()
    if len(text) > 500:
        text = text[:500] + "..."
    return f"{response.status_code} {response.reason}: {text or response.url}"


def build_seedream_generation_prompt(product: dict[str, Any], role: str, index: int, sku_text: str = "") -> str:
    title = clean_html_text(str(product.get("title") or "商品"))
    props = template_property_pairs(product.get("properties", {}) or {})
    prop_text = "、".join(f"{key}:{value}" for key, value in list(props.items())[:8])
    if role == "sku":
        return (
            "以参考图为依据重新生成一张1:1正方形SKU选项图，不要在原图上贴补丁。\n"
            "必须保持商品主体、结构、颜色、材质、比例和用途一致，只体现指定SKU差异。\n"
            f"商品：{title}\nSKU：{sku_text or '標準'}\n属性：{prop_text}\n"
            "要求：商品清晰居中，背景干净但不要纯白底，颜色/规格必须符合SKU描述；不要生成任何文字，SKU文字将由后端单独渲染；无Logo、无水印、无二维码、无人脸、无多余装饰。"
        )
    if role == "detail":
        return (
            "以参考图为依据重新生成一张商品详情说明图，不要在原图上贴补丁。\n"
            "商品主体和结构必须一致，适合放在妙手商品详情描述中。\n"
            f"商品：{title}\n属性：{prop_text}\n"
            f"画面主题第{index}张：展示使用场景、功能细节、尺寸感、材质质感或安装/收纳方式之一。\n"
            "要求：真实日本电商风，干净美观，宽度统一、适合详情页纵向浏览，不要纯白底；不要生成任何文字，商品说明文字将由后端单独渲染；原图中文要删除并补全背景；"
            "删除中文、Logo、水印、二维码、联系方式、侵权/IP元素；出现真人脸时替换为不存在的真实日本成年模特脸，保持真人摄影质感，禁止漫画脸、卡通脸、遮挡脸、马赛克脸。"
            "如出现真人/模特或手部，人体必须自然完整，双手和手臂数量正确、不断裂、不变形；所有商品都必须符合真实使用/佩戴/拿取/摆放逻辑，不能穿模、悬空、反重力或出现不合理物理关系。"
        )
    return (
        "以参考图为依据重新生成一张1:1正方形商品主图，不要在原图上贴补丁，不要做难看的白块覆盖。\n"
        "商品主体和结构必须一致，不改变颜色/规格/用途。\n"
        f"商品：{title}\n属性：{prop_text}\n"
        f"主图第{index}张：干净高级的日本电商风，突出商品主体、质感和使用价值。\n"
        "要求：主体清晰、构图舒服、吸引日本消费者点击，背景简洁，可适度生活化但不能出现不一致商品；"
        "不要纯白底或白底抠图；不要生成任何文字，商品卖点文字将由后端单独渲染；中文直接删除并补全背景；无Logo、无水印、无二维码、无大块文字、无侵权元素。"
        "出现真人脸时替换为不存在的真实日本成年模特脸，保持真人摄影质感，禁止漫画脸、卡通脸、遮挡脸、马赛克脸。"
        "如出现真人/模特或手部，人体必须自然完整，双手和手臂数量正确、不断裂、不变形；所有商品都必须符合真实使用/佩戴/拿取/摆放逻辑，不能穿模、悬空、反重力或出现不合理物理关系。"
    )


def build_fast_clean_image_prompt(product: dict[str, Any], role: str, sku_text: str = "") -> str:
    title = clean_html_text(str(product.get("title") or "商品"))
    role_text = {
        "main": "产品主图",
        "detail": "商品详情图",
        "sku": f"SKU选项图，SKU为：{sku_text or '标准款'}",
    }.get(role, "商品图")
    return (
        f"快速商品净图任务。这张图片用于{role_text}。\n"
        f"商品参考：{title}\n"
        "只保留原图中的真实商品主体和原有自然背景，删除除此之外的全部元素。\n"
        "必须删除所有中文、日语、英文、数字说明、价格、参数、促销标签、贴纸、Logo、水印、二维码、联系方式、平台标识、店铺信息和侵权/IP元素。\n"
        "必须删除人物、真人脸、模特、手、手臂、身体、动物和与商品无关的道具；删除后自然补全原背景，不能留下白块、色块、马赛克、模糊痕迹或拼贴边缘。\n"
        "商品本身必须原样锁定：结构、轮廓、颜色、材质、纹理、配件、比例、数量、朝向和SKU差异均不得改变，不得重新设计或新增商品部件。\n"
        "不要新增任何文字、人物、装饰、道具或其他商品。画面保持清晰、自然、干净，突出商品主体；主图和SKU图保持1:1，详情图保持原图比例和统一宽度。"
    )


def build_seedream_image_edit_prompt(
    product: dict[str, Any],
    analysis: dict[str, Any],
    config: ModelConfig,
    role: str = "main",
    sku_text: str = "",
) -> str:
    pairs: list[str] = []
    for item in analysis.get("text_regions", []) or []:
        if not isinstance(item, dict):
            continue
        source = clean_html_text(str(item.get("source_text") or ""))
        japanese = clean_html_text(str(item.get("japanese_text") or ""))
        if source and japanese:
            pairs.append(f"{source} -> {japanese}")
    remove_notes: list[str] = []
    for item in analysis.get("remove_regions", []) or []:
        if not isinstance(item, dict):
            continue
        reason = clean_html_text(str(item.get("reason") or "风险文字/标识"))
        remove_notes.append(reason)
    quality = "高清商用电商图" if "pro" in model_config_search_text(config).lower() else "批量商品图"
    replacements = "\n".join(f"- {item}" for item in pairs) or "- 将图中所有中文识别后翻译为自然日语"
    removals = "\n".join(f"- {item}" for item in remove_notes[:8]) or "- 无"
    title = clean_html_text(str(product.get("title") or "商品"))
    role_rule = {
        "main": "这张用于产品主图：必须吸引日本消费者购买欲，干净高级，主体突出，5-9张主图风格一致。",
        "detail": "这张用于详情描述：可以展示功能、材质、尺寸、使用场景，但不要像廉价广告图。",
        "sku": f"这张用于SKU选项图片：必须符合SKU `{sku_text}` 的描述，商品主体一致。",
    }.get(role, "这张用于商品图。")
    if role == "detail":
        text_rule = (
            "3. 详情图允许出现日语文字，但只允许把原图中文按下方对照关系替换成自然日语；"
            "必须在原文字相同区域或合理相邻区域内完成，自动匹配原图字号、字重、颜色、行距和排版，背景要无痕修复，不能像贴补丁、白块、色块或后加标签。"
        )
        negative_text_rule = "不要残留中文，不要新增无关文字，不要随机文字，不要无意义日语，不要模糊/乱码日语，不要文字遮挡商品。"
    else:
        text_rule = "3. 图片内所有原有文字都删除并补全背景；不要生成任何新文字、日语、英文、数字说明、标题、广告语或装饰字。"
        negative_text_rule = "不要残留中文，不要生成任何文字，不要随机文字，不要无意义日语，不要生成模糊/乱码日语，不要遮挡商品。"
    return (
        f"图生图，参考图重新生成任务，输出适合妙手导入的{quality}。\n"
        "严格遵守以下规则：\n"
        "1. 不要在原图上贴补丁、贴白块或覆盖文字框；请依据参考图重新生成一张干净完整的商品图。\n"
        "2. 商品主体、实物结构、颜色、材质纹理、比例、SKU差异和用途必须保持一致，不要重新设计商品。\n"
        f"{text_rule}\n"
        "4. 不能在窗户、墙面、衣服、地面、天空、建筑玻璃等背景上生成文字，不能遮挡商品主体。\n"
        "5. 删除店铺名、平台标识、品牌Logo、水印、二维码、联系方式、1688、阿里巴巴、厂家、批发、专利、侵权/IP风险元素。\n"
        "6. 出现真人脸时，必须替换为不存在的真实日本成年模特脸，肤质、表情、光影自然，保持真人摄影质感；禁止漫画脸、卡通脸、遮挡脸、马赛克脸，不能保留原真人面部特征。\n"
        "7. 如果画面有人体/模特：必须完整真实，双手和手臂数量正确，不能断手、断臂、多手、畸形手指，不能突然多出一只手；姿势必须符合现实物理。\n"
        "8. 所有品类都必须符合真实使用逻辑：穿戴类要符合人体穿戴关系，箱包类要符合肩背/手提/斜挎关系，家居类要符合摆放承重关系，工具/户外/厨房类要符合真实握持和使用方式；不能穿模、悬空、反重力、错位或结构不合理。\n"
        "9. 画面要像日本电商商品图：高级、清爽、清晰、有购买欲，使用自然浅色背景、生活化背景或参考图延展背景，不要纯白底或白底抠图，不能出现色块遮挡、马赛克遮挡、廉价拼贴感、白色说明框、半透明文字面板、贴纸角标、大标题块。\n"
        f"10. {role_rule} 主图和SKU图保持1:1正方形；详情图保持统一宽度、适合详情页纵向浏览。\n"
        f"商品参考标题：{title}\n"
        "文字替换对照：\n"
        f"{replacements}\n"
        "需要清除的风险元素：\n"
        f"{removals}\n"
        f"负面要求：不要改动商品主体，不要生成不一致款式，不要新增无关物体，不要模糊商品，{negative_text_rule}不要漫画化人物，不要人体结构错误，不要物理关系错误。"
    )


def image_from_generation_response(payload: dict[str, Any]) -> Image.Image | None:
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0] if isinstance(data[0], dict) else {}
        b64_json = first.get("b64_json") or first.get("image")
        if isinstance(b64_json, str) and b64_json:
            if b64_json.startswith("data:image"):
                b64_json = b64_json.split(",", 1)[-1]
            return Image.open(BytesIO(base64.b64decode(b64_json)))
        url = first.get("url")
        if isinstance(url, str) and url:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content))
    for key in ("b64_json", "image"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            if value.startswith("data:image"):
                value = value.split(",", 1)[-1]
            return Image.open(BytesIO(base64.b64decode(value)))
    url = payload.get("url")
    if isinstance(url, str) and url:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content))
    return None


def add_safe_japanese_labels(
    image: Image.Image,
    product: dict[str, Any],
    role: str = "main",
    sku_text: str = "",
    analysis: dict[str, Any] | None = None,
    variant: int = 1,
) -> Image.Image:
    labels = safe_japanese_image_labels(product, role=role, sku_text=sku_text, analysis=analysis, variant=variant)
    if not labels:
        return image
    base = ImageOps.exif_transpose(image).convert("RGBA")
    draw = ImageDraw.Draw(base)
    font_path = pick_japanese_font()
    if role == "sku":
        font_size = max(28, min(46, base.width // 18))
        font = ImageFont.truetype(font_path, size=font_size) if font_path else ImageFont.load_default()
        draw_label_chip(draw, label_position(base.size, variant, role), labels[0], font, fill=(30, 34, 40), bg=(255, 255, 255, 225))
        return base
    if role == "detail":
        font_size = max(26, min(40, base.width // 28))
        font = ImageFont.truetype(font_path, size=font_size) if font_path else ImageFont.load_default()
        x, y = label_position(base.size, variant, role)
        for label in labels[:4]:
            y = draw_label_chip(draw, (x, y), label, font, fill=(28, 32, 38), bg=(255, 255, 255, 220)) + 12
        return base
    font_size = max(30, min(50, base.width // 24))
    font = ImageFont.truetype(font_path, size=font_size) if font_path else ImageFont.load_default()
    x, y = label_position(base.size, variant, role)
    for label in labels[:2]:
        y = draw_label_chip(draw, (x, y), label, font, fill=(28, 32, 38), bg=(255, 255, 255, 218)) + 12
    return base


def label_position(image_size: tuple[int, int], variant: int, role: str) -> tuple[int, int]:
    width, height = image_size
    margin_x = max(24, width // 32)
    margin_y = max(24, height // 32)
    if role == "sku":
        return (margin_x, margin_y)
    positions = [
        (margin_x, margin_y),
        (margin_x, max(margin_y, height - height // 4)),
        (max(margin_x, width - width // 2), margin_y),
        (margin_x, height // 2),
        (max(margin_x, width - width // 2), max(margin_y, height - height // 4)),
    ]
    return positions[(max(1, variant) - 1) % len(positions)]


def draw_label_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    bg: tuple[int, int, int, int],
) -> int:
    x, y = xy
    text = clean_html_text(text)
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    pad_x = 18
    pad_y = 12
    radius = 18
    rect = (x, y, x + width + pad_x * 2, y + height + pad_y * 2)
    draw.rounded_rectangle(rect, radius=radius, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, fill=fill, font=font)
    return rect[3]


def safe_japanese_image_labels(
    product: dict[str, Any],
    role: str = "main",
    sku_text: str = "",
    analysis: dict[str, Any] | None = None,
    variant: int = 1,
) -> list[str]:
    labels: list[str] = []
    title = fallback_japanese_title(str(product.get("title") or ""))
    props = template_property_pairs(product.get("properties", {}) or {})
    if role == "sku":
        sku_label = simplify_sku_name(sku_text or "標準")
        return [sku_label] if sku_label and sku_label != "標準" else []
    source_labels = clean_analysis_japanese_labels(analysis or {})
    if source_labels:
        rotated = rotate_list(source_labels, variant - 1)
        return rotated[:2 if role == "main" else 4]
    if role == "detail":
        for key, value in props.items():
            label = japanese_property_label(str(key), str(value))
            if label and label not in labels:
                labels.append(label)
            if len(labels) >= 4:
                break
        if not labels:
            labels.extend(generic_product_labels(title)[:3])
        return rotate_list(labels, variant - 1)[:4]
    labels.extend(rotate_list(generic_product_labels(title), variant - 1)[:2])
    return labels[:2]


def clean_analysis_japanese_labels(analysis: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for raw in translated_text_captions(analysis):
        label = sanitize_image_label(raw)
        if label and label not in labels:
            labels.append(label)
    return labels[:6]


def sanitize_image_label(value: str) -> str:
    text = clean_html_text(value)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ・,，、。")
    if not text or len(text) < 2:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return ""
    if not re.search(r"[ぁ-んァ-ヶー]", text):
        return ""
    banned = ("1688", "Alibaba", "阿里", "メーカー", "卸", "批発", "正規品", "公式")
    if any(token.lower() in text.lower() for token in banned):
        return ""
    return text[:34]


def rotate_list(values: list[str], offset: int) -> list[str]:
    if not values:
        return []
    offset = offset % len(values)
    return values[offset:] + values[:offset]


def japanese_property_label(key: str, value: str) -> str:
    key = clean_html_text(key)
    value = clean_html_text(value)
    if not value:
        return ""
    lower_key = key.lower()
    if any(token in key for token in ("材质", "材料", "面料", "素材")):
        return f"素材：{translate_short_property_value(value)}"
    if any(token in key for token in ("尺寸", "规格", "大小", "长", "宽", "高", "サイズ")):
        return f"サイズ：{normalize_dimension_text(value)}"
    if any(token in key for token in ("颜色", "カラー", "色")):
        return f"カラー：{translate_short_property_value(value)}"
    if any(token in key for token in ("重量", "重さ")):
        return f"重さ：{normalize_dimension_text(value)}"
    if "容量" in key:
        return f"容量：{normalize_dimension_text(value)}"
    if "用途" in key or "適用" in lower_key:
        return f"用途：{translate_short_property_value(value)}"
    return ""


def translate_short_property_value(value: str) -> str:
    replacements = {
        "白色": "ホワイト",
        "黑色": "ブラック",
        "粉色": "ピンク",
        "红色": "レッド",
        "蓝色": "ブルー",
        "绿色": "グリーン",
        "棕色": "ブラウン",
        "米色": "ベージュ",
        "灰色": "グレー",
        "军绿": "カーキ",
        "PU": "PU",
        "皮革": "レザー調",
        "人造革": "フェイクレザー",
        "聚酯": "ポリエステル",
        "尼龙": "ナイロン",
        "棉": "コットン",
        "铁": "スチール",
        "不锈钢": "ステンレス",
        "木": "木製",
        "塑料": "プラスチック",
        "日常": "デイリー",
        "通勤": "通勤",
        "外出": "お出かけ",
        "户外": "アウトドア",
        "折叠": "折りたたみ",
        "便携": "持ち運び",
    }
    result = clean_html_text(value)
    for source, target in replacements.items():
        result = result.replace(source, target)
    result = re.sub(r"[，、]+", "・", result)
    return result[:28]


def normalize_dimension_text(value: str) -> str:
    text = clean_html_text(value)
    text = text.replace("*", "×").replace("x", "×").replace("X", "×")
    text = text.replace("厘米", "cm").replace("公分", "cm").replace("毫米", "mm").replace("千克", "kg").replace("克", "g")
    return text[:32]


def generic_product_labels(title: str) -> list[str]:
    labels: list[str] = []
    if any(token in title for token in ("バッグ", "鞄", "ショルダー")):
        labels = ["デイリーに使いやすい", "上品なレザー調"]
    elif any(token in title for token in ("チェア", "椅子", "アウトドア")):
        labels = ["持ち運びやすい", "アウトドアに便利"]
    elif any(token in title for token in ("鍋敷き", "コースター", "キッチン")):
        labels = ["食卓になじむデザイン", "毎日使いやすい"]
    elif any(token in title for token in ("ワンピース", "スカート", "トップス", "シャツ")):
        labels = ["すっきり見えるシルエット", "着回しやすい"]
    else:
        labels = ["毎日使いやすい", "シンプルで実用的"]
    return labels


def image_to_jpeg_bytes(image: Image.Image, max_size: int = 900) -> bytes:
    temp = image.convert("RGB")
    temp.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    temp.save(buffer, "JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def apply_compliance_edits(image: Image.Image, analysis: dict[str, Any], relocate_text: bool = False) -> Image.Image:
    result = soften_common_watermark_zones(image.copy().convert("RGBA"))
    draw = ImageDraw.Draw(result)
    for region in analysis.get("remove_regions", []) or []:
        box = normalize_box(region.get("box"), result.size)
        if box:
            erase_region(result, box)
    for region in analysis.get("text_regions", []) or []:
        box = normalize_box(region.get("box"), result.size)
        japanese = str(region.get("japanese_text") or "").strip()
        if box:
            erase_region(result, box)
            if japanese and not relocate_text:
                draw_fitted_japanese(draw, box, japanese)
    return result


def translated_text_captions(analysis: dict[str, Any]) -> list[str]:
    captions: list[str] = []
    for region in analysis.get("text_regions", []) or []:
        japanese = clean_html_text(str(region.get("japanese_text") or ""))
        if japanese and japanese not in captions:
            captions.append(japanese)
    return captions[:4]


def has_heavy_text_overlay(analysis: dict[str, Any], image_size: tuple[int, int]) -> bool:
    width, height = image_size
    image_area = max(width * height, 1)
    text_boxes = []
    for region in (analysis.get("text_regions", []) or []):
        box = normalize_box(region.get("box"), image_size)
        if box:
            text_boxes.append(box)
    remove_text_boxes = []
    for region in (analysis.get("remove_regions", []) or []):
        reason = str(region.get("reason") or "").lower()
        if any(token in reason for token in ("text", "文字", "watermark", "水印", "logo", "品牌", "contact", "qr")):
            box = normalize_box(region.get("box"), image_size)
            if box:
                remove_text_boxes.append(box)
    boxes = text_boxes + remove_text_boxes
    if not boxes:
        return False

    total_area = sum((right - left) * (bottom - top) for left, top, right, bottom in boxes)
    largest_area = max((right - left) * (bottom - top) for left, top, right, bottom in boxes)
    central_boxes = [box for box in boxes if intersects_center(box, image_size)]
    central_area = sum((right - left) * (bottom - top) for left, top, right, bottom in central_boxes)
    return (
        largest_area / image_area >= 0.10
        or total_area / image_area >= 0.16
        or central_area / image_area >= 0.08
        or len(text_boxes) >= 6
    )


def intersects_center(box: tuple[int, int, int, int], image_size: tuple[int, int]) -> bool:
    width, height = image_size
    center_box = (int(width * 0.22), int(height * 0.18), int(width * 0.78), int(height * 0.82))
    left, top, right, bottom = box
    c_left, c_top, c_right, c_bottom = center_box
    return not (right <= c_left or left >= c_right or bottom <= c_top or top >= c_bottom)


def normalize_box(raw_box: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_box, list) or len(raw_box) != 4:
        return None
    width, height = image_size
    try:
        x, y, w, h = [float(value) for value in raw_box]
    except (TypeError, ValueError):
        return None
    if 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1:
        x, y, w, h = x * width, y * height, w * width, h * height
    pad = max(8, int(min(width, height) * 0.015))
    left = max(0, int(x) - pad)
    top = max(0, int(y) - pad)
    right = min(width, int(x + w) + pad)
    bottom = min(height, int(y + h) + pad)
    return (left, top, right, bottom) if right > left and bottom > top else None


def erase_region(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    fill = estimate_border_color(image, box)
    patch = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), fill)
    image.paste(patch, box)


def estimate_border_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    width, height = image.size
    left, top, right, bottom = box
    sample_boxes = [
        (max(0, left - 12), top, left, bottom),
        (right, top, min(width, right + 12), bottom),
        (left, max(0, top - 12), right, top),
        (left, bottom, right, min(height, bottom + 12)),
    ]
    pixels: list[tuple[int, int, int, int]] = []
    for sample in sample_boxes:
        if sample[2] <= sample[0] or sample[3] <= sample[1]:
            continue
        crop = image.crop(sample).resize((1, 1), Image.Resampling.BOX).convert("RGBA")
        pixels.append(crop.getpixel((0, 0)))
    if not pixels:
        return (255, 255, 255, 255)
    channels = list(zip(*pixels))
    return tuple(int(sum(channel) / len(channel)) for channel in channels)  # type: ignore[return-value]


def draw_fitted_japanese(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    font_path = pick_japanese_font()
    for size in range(min(44, max(14, height - 8)), 11, -2):
        font = ImageFont.truetype(font_path, size=size) if font_path else ImageFont.load_default()
        lines = wrap_text_for_box(draw, text, font, width - 12)
        line_heights = [text_bbox_height(draw, line, font) + 4 for line in lines]
        if sum(line_heights) <= height - 8:
            y = top + max(4, (height - sum(line_heights)) // 2)
            for line, line_height in zip(lines, line_heights):
                draw.text((left + 6, y), line, fill=(25, 28, 32, 255), font=font)
                y += line_height
            return


def pick_japanese_font() -> str | None:
    for path in (
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    ):
        if Path(path).exists():
            return path
    return None


def wrap_text_for_box(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if not current or text_bbox_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines[:3]


def text_bbox_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def text_bbox_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def save_standard_product_image(image: Image.Image, output_path: Path, role: str = "main", quality: int = 92) -> None:
    final_image = standardize_product_image(image, role=role)
    final_image.save(output_path, "JPEG", quality=quality, optimize=True, progressive=True)


def standardize_product_image(image: Image.Image, role: str = "main") -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGBA")
    if role == "detail":
        width = DETAIL_IMAGE_WIDTH
        ratio = width / max(image.width, 1)
        height = max(600, int(image.height * ratio))
        height = min(height, 3200)
        detail = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        detail = ImageEnhance.Sharpness(detail).enhance(1.12)
        detail = ImageEnhance.Contrast(detail).enhance(1.03)
        detail = ImageEnhance.Color(detail).enhance(1.02)
        return detail
    image = trim_outer_light_border(image)
    base = Image.new("RGB", image.size, (255, 255, 255))
    base.paste(image.convert("RGB"), (0, 0), image if image.mode == "RGBA" else None)
    canvas = ImageOps.fit(base, MAIN_IMAGE_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.15)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.04)
    canvas = ImageEnhance.Color(canvas).enhance(1.03)
    return canvas


def enhance_product_image(image: Image.Image, captions: list[str] | None = None, role: str = "main") -> Image.Image:
    if role == "detail":
        return standardize_product_image(image, role=role)
    captions = [caption for caption in (captions or []) if caption]
    target_size = MAIN_IMAGE_SIZE
    caption_height = 220 if captions else 0
    base = trim_outer_light_border(ImageOps.exif_transpose(image).convert("RGBA"))
    rgb_base = Image.new("RGB", base.size, (255, 255, 255))
    rgb_base.paste(base.convert("RGB"), (0, 0), base if base.mode == "RGBA" else None)
    if caption_height:
        canvas = Image.new("RGB", MAIN_IMAGE_SIZE, (255, 255, 255))
        content = ImageOps.fit(
            rgb_base,
            (target_size[0], target_size[1] - caption_height),
            Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        canvas.paste(content, (0, caption_height))
    else:
        canvas = ImageOps.fit(rgb_base, MAIN_IMAGE_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if captions:
        draw_caption_band(canvas, captions, caption_height)
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.25)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.06)
    canvas = ImageEnhance.Color(canvas).enhance(1.04)
    return canvas


def trim_outer_light_border(image: Image.Image) -> Image.Image:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    rgb = source.convert("RGB")
    width, height = rgb.size
    if width < 20 or height < 20:
        return source
    pixels = rgb.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if not (red >= 245 and green >= 245 and blue >= 245):
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return source
    left, right = min(xs), max(xs) + 1
    top, bottom = min(ys), max(ys) + 1
    crop_width = right - left
    crop_height = bottom - top
    if crop_width < width * 0.35 or crop_height < height * 0.35:
        return source
    margin_x = max(0, int(crop_width * 0.015))
    margin_y = max(0, int(crop_height * 0.015))
    box = (
        max(0, left - margin_x),
        max(0, top - margin_y),
        min(width, right + margin_x),
        min(height, bottom + margin_y),
    )
    if box == (0, 0, width, height):
        return source
    return source.crop(box)


def draw_caption_band(canvas: Image.Image, captions: list[str], height: int) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, height), fill=(255, 255, 255))
    font_path = pick_japanese_font()
    title_font = ImageFont.truetype(font_path, size=42) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, size=32) if font_path else ImageFont.load_default()
    y = 26
    for index, caption in enumerate(captions[:3]):
        font = title_font if index == 0 else body_font
        prefix = "" if index == 0 else "・"
        lines = wrap_text_for_box(draw, prefix + caption, font, canvas.width - 120)
        for line in lines[:2 if index == 0 else 1]:
            draw.text((60, y), line, fill=(24, 28, 34), font=font)
            y += text_bbox_height(draw, line, font) + 12
        if y > height - 42:
            break


def soften_common_watermark_zones(image: Image.Image) -> Image.Image:
    result = image.copy()
    width, height = result.size
    zones = [
        (0, 0, int(width * 0.28), int(height * 0.12)),
        (int(width * 0.72), 0, width, int(height * 0.12)),
        (0, int(height * 0.88), width, height),
    ]
    for box in zones:
        patch = result.crop(box)
        bright = Image.new("RGBA", patch.size, (255, 255, 255, 92))
        patch = Image.alpha_composite(patch.convert("RGBA"), bright).filter(ImageFilter.SMOOTH_MORE)
        result.paste(patch, box)
    return result


def upload_images_to_ecs(task_id: str, image_paths: list[Path]) -> None:
    if not DEFAULT_ASSET_UPLOAD_KEY.exists():
        raise AutoPublishError(f"ECS 上传密钥不存在：{DEFAULT_ASSET_UPLOAD_KEY}")
    remote_dir = f"{DEFAULT_ASSET_UPLOAD_DIR.rstrip('/')}/{task_id}"
    target = f"{DEFAULT_ASSET_UPLOAD_USER}@{DEFAULT_ASSET_UPLOAD_HOST}"
    ssh_base = [
        "ssh",
        "-i",
        str(DEFAULT_ASSET_UPLOAD_KEY),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=NUL",
        target,
    ]
    scp_base = [
        "scp",
        "-i",
        str(DEFAULT_ASSET_UPLOAD_KEY),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=NUL",
    ]
    run_subprocess(ssh_base + [f"mkdir -p {shell_quote(remote_dir)} && chown -R www-data:www-data {shell_quote(remote_dir)}"])
    run_subprocess(scp_base + [*[str(path) for path in image_paths], f"{target}:{remote_dir}/"])
    run_subprocess(ssh_base + [f"chown -R www-data:www-data {shell_quote(remote_dir)} && chmod -R a+rX {shell_quote(remote_dir)}"])


def upload_images_to_miaoshou_picture_space(image_paths: list[Path], task_id: str = "") -> dict[Path, str]:
    storage_path = miaoshou_storage_state_path_for_task(task_id)
    if not storage_path.exists():
        raise AutoPublishError("妙手图片空间上传失败：缺少妙手登录态，请先完成一次妙手登录。")
    session = requests.Session()
    try:
        state = json.loads(storage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutoPublishError("妙手图片空间上传失败：妙手登录态文件无法读取。") from exc
    for cookie in state.get("cookies", []):
        domain = str(cookie.get("domain") or "")
        if "91miaoshou.com" not in domain:
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        session.cookies.set(str(name), str(value), domain=domain.lstrip("."), path=str(cookie.get("path") or "/"))
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Origin": "https://erp.91miaoshou.com",
            "Referer": "https://erp.91miaoshou.com/common_collect_box/items",
            "Accept": "application/json, text/plain, */*",
        }
    )
    uploaded: dict[Path, str] = {}
    for image_path in image_paths:
        status_code: int | None = None
        try:
            with image_path.open("rb") as file_obj:
                response = session.post(
                    MIAOSHOU_PICTURE_UPLOAD_URL,
                    data={"uploadType": "file", "scene": "product"},
                    files={"uploadImgFile": (image_path.name, file_obj, "image/jpeg")},
                    timeout=60,
                )
            status_code = response.status_code
            if response.status_code in (401, 403):
                record_api_usage(
                    task_id,
                    provider="miaoshou",
                    purpose="picture_space_upload",
                    model="picture_upload_api",
                    endpoint=MIAOSHOU_PICTURE_UPLOAD_URL,
                    success=False,
                    image_count=1,
                    status_code=status_code,
                    error=f"{image_path.name} 妙手登录态已失效",
                )
                raise AutoPublishError(f"妙手图片空间上传失败：{image_path.name} 妙手登录态已失效，请重新登录妙手后再运行。")
            response.raise_for_status()
            payload = response.json()
        except AutoPublishError:
            raise
        except (OSError, requests.RequestException, ValueError) as exc:
            record_api_usage(
                task_id,
                provider="miaoshou",
                purpose="picture_space_upload",
                model="picture_upload_api",
                endpoint=MIAOSHOU_PICTURE_UPLOAD_URL,
                success=False,
                image_count=1,
                status_code=status_code,
                error=f"{image_path.name} {exc}",
            )
            raise AutoPublishError(f"妙手图片空间上传失败：{image_path.name} {exc}") from exc
        if payload.get("result") != "success" or not payload.get("picturePath"):
            reason = payload.get("reason") or payload.get("message") or str(payload)[:200]
            record_api_usage(
                task_id,
                provider="miaoshou",
                purpose="picture_space_upload",
                model="picture_upload_api",
                endpoint=MIAOSHOU_PICTURE_UPLOAD_URL,
                success=False,
                image_count=1,
                status_code=status_code,
                error=f"{image_path.name} {reason}",
            )
            raise AutoPublishError(f"妙手图片空间上传失败：{image_path.name} {reason}")
        uploaded[image_path] = str(payload["picturePath"])
        record_api_usage(
            task_id,
            provider="miaoshou",
            purpose="picture_space_upload",
            model="picture_upload_api",
            endpoint=MIAOSHOU_PICTURE_UPLOAD_URL,
            success=True,
            image_count=1,
            status_code=status_code,
            meta={"file": image_path.name},
        )
    return uploaded


def run_subprocess(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        raise AutoPublishError(f"ECS 图片上传失败：{exc.stderr or exc.stdout}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AutoPublishError(f"ECS 图片上传超时：{exc}") from exc


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def optimize_for_japan_listing(
    db: Session,
    product: dict[str, Any],
    task_id: str,
    target_language: str = "ja",
    image_mode: str = "fast",
    before_image_upload_callback: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    language = normalize_target_language(target_language)
    meta = target_language_meta(language)
    ai_result = call_listing_ai(db, product, language, task_id=task_id)
    title_key = "english_title" if language == "en" else "japanese_title"
    title = ensure_localized_title(ai_result.get(title_key) or ai_result.get("japanese_title") or "", product, language)
    description = ai_result.get("detail_description") or ai_result.get("description") or ""
    if not looks_like_target_language(description, language):
        description = build_description(product, language)
    description = sanitize_listing_copy(description)
    sku_map = ai_result.get("sku_names") if isinstance(ai_result.get("sku_names"), dict) else {}
    image_result = prepare_compliant_images(
        task_id,
        product,
        image_mode=image_mode,
        target_language=language,
        before_image_upload_callback=before_image_upload_callback,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
    main_images = importable_image_urls(image_result.get("main_images", []) or [], limit=MAIN_IMAGE_TARGET)
    detail_images = importable_image_urls(image_result.get("detail_images", []) or [], limit=DETAIL_IMAGE_OUTPUT_LIMIT)
    sku_image_map = image_result.get("sku_image_map", {}) if isinstance(image_result.get("sku_image_map"), dict) else {}

    source_skus = [sku for sku in product.get("skus", []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
    if not source_skus:
        source_skus = [{"spec1": "標準", "spec2": "", "price": product.get("price") or "0", "stock": 100, "image_url": ""}]

    shipping_fee = safe_price(product.get("shipping_fee"))
    skus = []
    used_spec_keys: set[str] = set()
    for index, sku in enumerate(source_skus[:20], start=1):
        original_spec = str(sku.get("spec1") or "標準")
        mapped_spec = str(sku_map.get(original_spec) or original_spec or meta["standard_sku"])
        if not sku_translation_preserves_critical_tokens(original_spec, mapped_spec):
            mapped_spec = original_spec
        if is_garbled_sku_spec(mapped_spec):
            mapped_spec = fallback_sku_name_from_index(original_spec, index, language)
        spec1 = simplify_sku_name(mapped_spec, language)
        if spec1 == meta["standard_sku"] and is_garbled_sku_spec(original_spec):
            spec1 = fallback_sku_name_from_index(original_spec, index, language)
        spec2 = simplify_sku_name(str(sku.get("spec2") or ""), language) if sku.get("spec2") else ""
        spec1, spec2 = unique_sku_specs(spec1, spec2, original_spec, used_spec_keys, language)
        if not spec1:
            continue
        original_image = normalize_image_url(str(sku.get("image_url") or ""))
        sku_image = sku_image_map.get(sku_identity(sku)) or ""
        skus.append(
            sku
            | {
                "spec1": spec1,
                "spec2": spec2,
                "raw_spec1": original_spec,
                "raw_spec2": str(sku.get("spec2") or ""),
                "raw_image_url": original_image,
                "platform_sku": f"1688-{product.get('offer_id') or 'item'}-{index:03d}",
                "image_url": sku_image,
                "source_price": safe_price(sku.get("price") or product.get("price")),
                "price": price_with_shipping(sku.get("price") or product.get("price"), shipping_fee),
                "stock": int(float(sku.get("stock") or 100)),
            }
        )
    if not skus:
        skus = [{"spec1": "標準", "spec2": "", "price": price_with_shipping(product.get("price"), shipping_fee), "stock": 100, "image_url": ""}]
    deleted_sku_specs = [
        " / ".join([part for part in (str(sku.get("spec1") or ""), str(sku.get("spec2") or "")) if part]).strip() or str(sku.get("raw_spec1") or "未命名SKU")
        for sku in skus
        if normalize_image_url(str(sku.get("raw_image_url") or sku.get("original_image_url") or sku.get("source_image_url") or ""))
        and not is_importable_image_url(str(sku.get("image_url") or ""))
    ]
    if deleted_sku_specs:
        image_errors = image_result.setdefault("errors", [])
        image_errors.append(
            f"SKU图处理/上传后缺失，已按要求删除对应 SKU，不阻断商品。删除规格：{'、'.join(deleted_sku_specs[:30])}"
            + ("。" if len(deleted_sku_specs) <= 30 else f" 等 {len(deleted_sku_specs)} 个。")
        )
        skus = [
            sku
            for sku in skus
            if not (
                normalize_image_url(str(sku.get("raw_image_url") or sku.get("original_image_url") or sku.get("source_image_url") or ""))
                and not is_importable_image_url(str(sku.get("image_url") or ""))
            )
        ]
    if not skus:
        image_result.setdefault("errors", []).append("SKU图处理后没有可保留的 SKU，商品无法生成有效规格。")
    skus_with_source_image = [sku for sku in skus if normalize_image_url(str(sku.get("raw_image_url") or sku.get("original_image_url") or sku.get("source_image_url") or ""))]
    clean_sku_images = [str(sku.get("image_url") or "") for sku in skus if is_importable_image_url(str(sku.get("image_url") or ""))]
    sku_image_missing_specs: list[str] = []
    return product | {
        "optimized_title": title[:120],
        "detail_description": description[:1800],
        "optimized_skus": skus,
        "clean_main_images": main_images,
        "clean_detail_images": detail_images,
        "clean_sku_images": clean_sku_images,
        "sku_image_required": len(skus_with_source_image),
        "sku_image_missing_specs": sku_image_missing_specs,
        "sku_image_deleted_specs": deleted_sku_specs,
        "sku_image_deleted_all": bool(deleted_sku_specs and not skus),
        "image_notice": image_result.get("notice", "图片已完成基础合规处理。"),
        "image_result": image_result,
        "price_includes_shipping": True,
    }


def call_listing_ai(db: Session, product: dict[str, Any], target_language: str = "ja", task_id: str = "") -> dict[str, Any]:
    config = select_auto_publish_model_config(db, "listing_text")
    if not config or not config.api_key_encrypted or not config.base_url or not config.model_name:
        return {}
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    language = normalize_target_language(target_language)
    meta = target_language_meta(language)
    title_key = "english_title" if language == "en" else "japanese_title"
    prompt = {
        "source_title": product.get("title"),
        "category": product.get("category"),
        "properties": product.get("properties"),
        "price_cny": product.get("price"),
        "sku_names": [item.get("spec1") for item in product.get("skus", [])[:30] if not is_bad_sku_name(str(item.get("spec1") or ""))],
        "target_market": meta["market"],
        "target_language": meta["native"],
        "goal": f"生成适合{meta['market']}的商品标题、详情描述和 SKU 名称。",
        "output_schema": {
            title_key: f"自然的{meta['label']}商品标题",
            "detail_description": f"{meta['label']}HTML商品说明",
            "sku_names": {"原SKU名": f"短而清楚的{meta['label']}SKU名"},
        },
        "rules": [
            f"标题必须是自然{meta['label']}，符合目标市场购物搜索习惯，前半是自然商品名，后半适度加搜索词，通顺但不过度堆词。",
            "不要出现 1688、阿里巴巴、厂家、爆款、新款、北欧风格、跨境、批发、源头、一件代发、现货等供应链词。",
            "不要出现侵权风险词：品牌名、IP角色名、动漫名、官方、正規品、专利、特許、専利、专利款、专利设计等。",
            f"描述必须围绕商品本身特点，写成吸引{meta['market']}消费者购买的自然销售文案，不要写成产品属性表。",
            "描述必须根据当前商品生成，必须体现商品类型、外观/玩法/用途/适用场景等从标题、类目、SKU或属性中能确认的信息；禁止输出可套用到任何商品的空泛描述。",
            "描述里不要输出 属性名:属性值 的列表，不要出现材质、产地、货号、平台、销售地区、是否跨境、货源类型等供应链字段。",
            "不得编造材质、认证、功效、适用人群、尺寸、配送时效或售后承诺。",
            "不要出现几天到、当日発送、翌日配送、最安、最高級、絶対、100%保証、爆売れ、必買等夸大或承诺文案。",
            "SKU 名称必须简短日语、清楚好懂，删除复杂冗余文字和专利相关词。",
            "SKU 只保留买家选择需要的信息，例如商品类型、颜色、大小、包装方式、核心款式；不要保留整句商品标题。",
            "如果包装方式是 SKU 区分条件，必须保留并翻译，例如：pp袋黑色->PP袋 ブラック，盒装灰色->箱入り グレー。",
            "SKU 不要出现中文、重量、货源词、平台词、专利词、品牌/IP词；但 pp袋、盒装、袋装、彩盒等用于区分 SKU 的包装方式必须保留。",
            "只返回 JSON，不要解释。",
        ],
    }
    payload = {
        "model": config.model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"你是面向{meta['market']}的跨境电商商品编辑。只输出JSON。"
                    f"{title_key}必须是目标买家自然使用的{meta['label']}，不能是机翻腔。"
                    "タイトル、説明、SKUには1688、阿里巴巴、メーカー直送、爆売れ、新作、北欧風、越境、卸売、仕入れ元、代行、即納などの供給側表現を含めない。"
                    "ブランド名、IP名、キャラクター名、公式、正規品、特許、専利、特許デザインなど権利侵害や専利リスクのある表現は禁止。"
                    f"detail_descriptionは商品の実際の魅力を伝える{meta['label']}HTMLの販売文にし、属性表やスペック表を書かない。"
                    "detail_descriptionは必ずこの商品の種類、見た目、使い方、利用シーンなど確認できる情報に基づいて書き、どの商品にも使える汎用文にしない。"
                    "材質、産地、品番、プラットフォーム、販売地域、越境、仕入れ、貨源など供給側フィールドを入れない。"
                    "未確認の材質、認証、効能、配送日数、誇大表現を作らない。"
                    f"sku_namesは元SKU名から短く分かりやすい{meta['label']}SKU名へのマッピングにする。"
                    "SKUは商品種別、色、サイズ、包装方式、主要仕様だけに絞り、20文字以内を目安にする。"
                    "包装方式がSKUの違いを表す場合は必ず残す。例：pp袋黑色->PP袋 ブラック、盒装灰色->箱入り グレー。"
                    "中国語、重量、仕入れ表現、特許・ブランド・IP関連語は削除する。"
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
    }
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        response_payload = response.json()
        usage = usage_from_response_payload(response_payload)
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="listing_text_optimization",
            model=config.model_name or "",
            endpoint=endpoint,
            success=True,
            status_code=response.status_code,
            meta=model_config_usage_meta(config),
            **usage,
        )
        content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        return parsed if isinstance(parsed, dict) else {}
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        record_api_usage(
            task_id,
            provider=config.provider or "volcengine_ark",
            purpose="listing_text_optimization",
            model=config.model_name or "",
            endpoint=endpoint,
            success=False,
            error=str(exc),
            meta=model_config_usage_meta(config),
        )
        return {}


def select_auto_publish_model_config(db: Session, purpose: str) -> ModelConfig | None:
    configs = select_auto_publish_model_configs(db, purpose)
    return pick_from_pool(f"model:{purpose}", configs) if configs else None


def select_auto_publish_model_configs(db: Session, purpose: str) -> list[ModelConfig]:
    configs = db.scalars(
        select(ModelConfig).where(ModelConfig.status == 1).order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
    ).all()
    if not configs:
        return []

    if purpose == "image_generation":
        preferred = sort_by_model_priority(
            [item for item in configs if is_seedream_model(item)],
            DOUBAO_IMAGE_ENDPOINTS + DOUBAO_IMAGE_MODELS,
        )
    elif purpose == "image_text_translation":
        preferred = sort_by_model_priority(
            [item for item in configs if is_translation_model(item)],
            DOUBAO_TRANSLATION_ENDPOINTS + DOUBAO_TRANSLATION_MODELS,
        )
    else:
        preferred = sort_by_model_priority(
            [item for item in configs if is_doubao_text_model(item)],
            DOUBAO_TEXT_ENDPOINTS + DOUBAO_TEXT_MODELS,
        )
        if purpose == "image_analysis":
            vision = [item for item in preferred if config_has_any(item, ("vision", "视觉", "图片", "image"))]
            if vision:
                preferred = vision

    with_key = [item for item in preferred if item.api_key_encrypted and item.base_url and item.model_name]
    if with_key:
        return dedupe_model_config_pool(with_key)
    if purpose == "image_text_translation":
        return dedupe_model_config_pool(preferred) if preferred else []
    fallback = [item for item in configs if item.api_key_encrypted and item.base_url and item.model_name and not is_seedream_model(item)]
    if fallback:
        return dedupe_model_config_pool(fallback)
    return dedupe_model_config_pool(preferred or configs)


def dedupe_model_config_pool(configs: list[ModelConfig]) -> list[ModelConfig]:
    result: list[ModelConfig] = []
    seen: set[tuple[str, str, str]] = set()
    for config in configs:
        key = (str(config.base_url or ""), str(config.api_key_encrypted or ""), str(config.model_name or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(config)
    return result


def sort_by_model_priority(configs: list[ModelConfig], model_priority: tuple[str, ...]) -> list[ModelConfig]:
    priority = {model.lower(): index for index, model in enumerate(model_priority)}

    def key(config: ModelConfig) -> tuple[int, int, int]:
        search_text = model_config_search_text(config).lower()
        model_rank = next(
            (rank for model, rank in priority.items() if model in search_text),
            len(priority),
        )
        return (model_rank, -int(config.is_default or 0), -int(config.id or 0))

    return sorted(configs, key=key)


def is_doubao_text_model(config: ModelConfig) -> bool:
    value = model_config_search_text(config).lower()
    if (
        "auto_publish:image_text_translation" in value
        or "aimediakit" in value
        or "ai mediakit" in value
        or "media kit" in value
        or "mediakit" in value
        or "translate-image-text" in value
        or "remove-image-elements" in value
    ):
        return False
    if "auto_publish:listing_text" in value:
        return True
    return any(model.lower() in value for model in DOUBAO_TEXT_MODELS) or (
        ("doubao" in value or "豆包" in value or "ark" in value or "方舟" in value)
        and "seedream" not in value
    )


def is_seedream_model(config: ModelConfig) -> bool:
    value = model_config_search_text(config).lower()
    if "auto_publish:image_generation" in value or "auto_publish:image_edit" in value:
        return True
    return any(model.lower() in value for model in DOUBAO_IMAGE_MODELS) or "seedream" in value


def is_translation_model(config: ModelConfig) -> bool:
    value = model_config_search_text(config).lower()
    provider = (config.provider or "").lower()
    model_type = (config.model_type or "").lower()
    base_url = (config.base_url or "").lower()
    if model_type == "image_text_translation":
        return True
    if "auto_publish:image_text_translation" in value:
        return True
    if any(provider_name in provider for provider_name in MEDIAKIT_TRANSLATION_PROVIDERS):
        return True
    if any(endpoint.lower() in base_url for endpoint in MEDIAKIT_TRANSLATION_ENDPOINTS):
        return True
    return any(model.lower() in value for model in DOUBAO_TRANSLATION_MODELS) or any(
        endpoint.lower() in value for endpoint in DOUBAO_TRANSLATION_ENDPOINTS
    )


def config_has_any(config: ModelConfig, keywords: tuple[str, ...]) -> bool:
    value = model_config_search_text(config).lower()
    return any(keyword.lower() in value for keyword in keywords)


def model_config_search_text(config: ModelConfig) -> str:
    return " ".join(
        str(value or "")
        for value in (config.config_name, config.provider, config.base_url, config.model_name, config.remark)
    )

def ensure_japanese_title(title: str, product: dict[str, Any]) -> str:
    return ensure_localized_title(title, product, "ja")


def ensure_localized_title(title: str, product: dict[str, Any], target_language: str = "ja") -> str:
    title = sanitize_listing_copy(clean_html_text(title or ""))
    banned = banned_listing_pattern()
    language = normalize_target_language(target_language)
    if title and looks_like_target_language(title, language) and not re.search(banned, title):
        return title
    return fallback_localized_title(str(product.get("title") or ""), language)


def looks_like_japanese(value: str) -> bool:
    return bool(value and re.search(r"[ぁ-んァ-ヶー]", value))


def looks_like_target_language(value: str, target_language: str = "ja") -> bool:
    if normalize_target_language(target_language) == "en":
        return bool(value and re.search(r"[A-Za-z]", value))
    return looks_like_japanese(value)


def contains_cjk(value: str) -> bool:
    return bool(value and re.search(r"[\u4e00-\u9fff]", value))


def fallback_japanese_title(title: str) -> str:
    return fallback_localized_title(title, "ja")


def fallback_localized_title(title: str, target_language: str = "ja") -> str:
    if normalize_target_language(target_language) == "en":
        source = clean_html_text(title)
        lower = source.lower()
        if any(token in source for token in ("锅垫", "隔热垫", "防烫", "茶杯", "杯垫", "圣诞树", "树")):
            return "Heat-Resistant Trivet Kitchen Coaster Decorative Home Accessory"
        if any(token in source for token in ("连衣裙", "裙", "女装")):
            return "Women's Dress Elegant Casual Outfit Stylish Daily Wear"
        if any(token in source for token in ("水母", "八爪鱼", "章鱼", "鲨鱼", "鲍鱼", "跳舞", "儿童", "玩具")):
            return "Light-Up Dancing Toy Fun Motion Toy for Kids"
        if any(token in source for token in ("奖状", "证书", "文件夹", "画册", "收纳")):
            return "Certificate File Holder Document Organizer for School and Home"
        if "pet" in lower or any(token in source for token in ("宠物", "猫", "狗")):
            return "Pet Supplies Practical Daily Care Accessory"
        return "Practical Daily Use Item Convenient Home and Lifestyle Accessory"
    source = clean_html_text(title)
    lower = source.lower()
    if any(token in source for token in ("锅垫", "隔热垫", "防烫", "茶杯", "杯垫", "圣诞树", "树")):
        return "木製ツリー型鍋敷き 耐熱コースター キッチン雑貨 インテリア置物"
    if any(token in source for token in ("连衣裙", "裙", "女装")):
        return "レディースワンピース 上品デザイン きれいめ カジュアル おしゃれ"
    if any(token in source for token in ("奖状", "证书", "文件夹", "画册", "收纳")):
        return "賞状ファイル 証書収納ホルダー A4/A3対応 学生用 作品整理"
    if any(token in source for token in ("水母", "八爪鱼", "章鱼", "鲨鱼", "鲍鱼", "跳舞", "儿童", "玩具")):
        return "光るダンシングトイ 動きが楽しい子ども向け玩具"
    if "pet" in lower or any(token in source for token in ("宠物", "猫", "狗")):
        return "ペット用品 便利グッズ お手入れしやすい 日常使い"
    return "便利グッズ 暮らしを整える実用アイテム"

def build_description(product: dict[str, Any], target_language: str = "ja") -> str:
    safe_title_ja = ensure_localized_title("", product, "ja")
    safe_title_en = ensure_localized_title("", product, "en")
    category = clean_html_text(str(product.get("category") or ""))
    safe_props = template_property_pairs(product.get("properties", {}) or {})
    if normalize_target_language(target_language) == "ja":
        category_text = "子ども向け玩具" if any(token in category for token in ("儿童", "玩具", "母婴")) else (category if category and not contains_cjk(category) else "")
        prop_parts = []
        for key, value in list(safe_props.items())[:3]:
            if "颜色" in str(key) or "色" in str(key):
                prop_parts.append(f"カラー {simplify_sku_name(str(value), 'ja')}")
            elif not contains_cjk(str(key) + str(value)):
                prop_parts.append(f"{key}{value}")
        prop_text = "、".join(prop_parts)
    else:
        category_text = "Kids Toy" if any(token in category for token in ("儿童", "玩具", "母婴")) else (category if category and not contains_cjk(category) else "")
        prop_text = "; ".join(f"{key} {value}" for key, value in list(safe_props.items())[:3] if not contains_cjk(str(key) + str(value)))
    sku_names = [
        simplify_sku_name(str(item.get("spec1") or ""), target_language)
        for item in (product.get("skus") or [])[:6]
        if not is_bad_sku_name(str(item.get("spec1") or ""))
    ]
    unique_sku_names = list(dict.fromkeys(name for name in sku_names if name and name not in {"標準", "Standard"}))
    sku_text = "、".join(unique_sku_names[:4])
    if normalize_target_language(target_language) == "en":
        title = safe_title_en
        detail_bits = "; ".join(bit for bit in (category_text, prop_text, sku_text) if bit)
        return (
            f"<p>{title} is selected for buyers looking for a clear, easy-to-understand product with practical everyday appeal.</p>"
            f"<p>{'Key confirmed details: ' + detail_bits + '. ' if detail_bits else ''}The description is based on the product information parsed from the source listing.</p>"
            "<ul>"
            "<li>Highlights the actual product type and selectable variation</li>"
            "<li>Suitable for buyers who want a straightforward product choice</li>"
            "<li>Check the selected color or variation before ordering</li>"
            "</ul>"
            "<p>Colors may look slightly different depending on your screen.</p>"
        )
    title = safe_title_ja
    detail_bits = "、".join(bit for bit in (category_text, prop_text, sku_text) if bit)
    return (
        f"<p>{title}は、商品情報をもとに日本向けに分かりやすく整理したアイテムです。</p>"
        f"<p>{'確認できる内容：' + detail_bits + '。' if detail_bits else ''}カラーや仕様を選びやすく、商品画像とSKUを確認しながら選択できます。</p>"
        "<ul>"
        "<li>商品タイプとバリエーションが分かりやすい</li>"
        "<li>用途や見た目を画像で確認しながら選べる</li>"
        "<li>カラーや仕様違いを比較しやすい</li>"
        "</ul>"
        "<p>ご注文前にサイズやカラーをご確認ください。モニター環境により色味が実物と異なる場合があります。</p>"
    )


def banned_listing_pattern() -> str:
    return (
        r"1688|阿里巴巴|アリババ|厂家|メーカー直送|批发|卸売|源头|仕入れ元|跨境|越境|"
        r"一件代发|代行|现货|即納|爆款|爆売れ|新款|新作|北欧風|北欧风格|专利|專利|特許|専利|"
        r"公式|正規品|Disney|ディズニー|Nike|ナイキ|Adidas|アディダス|Sanrio|サンリオ"
    )


def sanitize_listing_copy(value: str) -> str:
    value = re.sub(banned_listing_pattern(), "", value or "", flags=re.IGNORECASE)
    value = re.sub(
        r"最安|最高級|必買|100%保証|絶対|当天发|当天發|当日発送|翌日配送|数日で届く|すぐ届く|ランキング\s*\d+\s*位|\d+\s*日到着",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r">\s+<", "><", value)
    return value.strip()

def build_miaoshou_import_xls(task_id: str, product: dict[str, Any]) -> Path:
    if not DEFAULT_TEMPLATE_PATH.exists():
        raise AutoPublishError(f"妙手导入模板不存在：{DEFAULT_TEMPLATE_PATH}")
    _ensure_runtime_dir()
    output_path = RUNTIME_DIR / f"miaoshou_import_{task_id}.xls"
    shutil.copyfile(DEFAULT_TEMPLATE_PATH, output_path)
    rows = miaoshou_rows(product)
    write_rows_to_xls(output_path, rows)
    return output_path


def build_miaoshou_import_xls_multi(task_id: str, products: list[dict[str, Any]]) -> Path:
    if not DEFAULT_TEMPLATE_PATH.exists():
        raise AutoPublishError(f"妙手导入模板不存在：{DEFAULT_TEMPLATE_PATH}")
    _ensure_runtime_dir()
    output_path = RUNTIME_DIR / f"miaoshou_import_batch_{task_id}.xls"
    shutil.copyfile(DEFAULT_TEMPLATE_PATH, output_path)

    rows: list[list[Any]] = []
    used_main_no: set[str] = set()
    for product_index, product in enumerate(products, start=1):
        product_rows = miaoshou_rows(product)
        if not product_rows:
            continue
        base_main_no = str(product_rows[0][0] or f"A{product_index:03d}").strip() or f"A{product_index:03d}"
        main_no = base_main_no
        if main_no in used_main_no:
            main_no = f"{base_main_no}-{product_index:02d}"
        used_main_no.add(main_no)
        for row in product_rows:
            row[0] = main_no
        rows.extend(product_rows)

    if not rows:
        raise AutoPublishError("没有可写入妙手模板的商品行。")
    write_rows_to_xls(output_path, rows)
    return output_path


def validate_template_images_from_miaoshou_space(product: dict[str, Any]) -> list[str]:
    image_result = product.get("image_result") if isinstance(product.get("image_result"), dict) else {}
    url_map = image_result.get("url_map") if isinstance(image_result.get("url_map"), dict) else {}
    uploaded_urls = {str(url).strip() for url in url_map.values() if str(url).strip()}
    errors: list[str] = []

    def check_urls(label: str, urls: list[Any]) -> None:
        for index, raw_url in enumerate(urls, start=1):
            url = str(raw_url or "").strip()
            if not url:
                errors.append(f"{label}第{index}张图片链接为空。")
            elif url not in uploaded_urls:
                errors.append(f"{label}第{index}张图片不是本次妙手图片空间上传返回的链接，已阻止导入。")

    check_urls("主图", list(product.get("clean_main_images") or []))
    check_urls("详情图", list(product.get("clean_detail_images") or []))
    for index, sku in enumerate(product.get("optimized_skus") or [], start=1):
        if not isinstance(sku, dict):
            continue
        raw_source = normalize_image_url(str(sku.get("raw_image_url") or ""))
        image_url = str(sku.get("image_url") or "").strip()
        if not raw_source:
            continue
        sku_name = " / ".join([part for part in (str(sku.get("spec1") or ""), str(sku.get("spec2") or "")) if part]).strip() or f"SKU{index}"
        if not image_url:
            errors.append(f"SKU `{sku_name}` 有源图但模板图片链接为空。")
        elif image_url not in uploaded_urls:
            errors.append(f"SKU `{sku_name}` 图片不是本次妙手图片空间上传返回的链接，已阻止导入。")
    return errors


def miaoshou_rows(product: dict[str, Any]) -> list[list[Any]]:
    main_no = f"A{product.get('offer_id') or datetime.utcnow().strftime('%H%M%S')}"
    main_images = importable_image_urls(product.get("clean_main_images", []), limit=9)
    detail_image_list = importable_image_urls(product.get("clean_detail_images", []), limit=DETAIL_IMAGE_OUTPUT_LIMIT)
    images = ",".join(main_images)
    detail_images = ",".join(detail_image_list)
    attrs = "；".join(f"{key}:{value}" for key, value in template_property_pairs(product.get("properties", {}) or {}).items())[:500]
    source_skus = product.get("optimized_skus") if "optimized_skus" in product else product.get("skus")
    skus = [sku for sku in (source_skus or []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
    if product.get("sku_image_deleted_all") and not skus:
        return []
    if not skus:
        skus = [{"spec1": "標準", "spec2": "", "price": product.get("price") or 0, "stock": 100, "image_url": main_images[0] if main_images else ""}]
    skus = dedupe_template_skus(skus)
    if not skus:
        skus = [{"spec1": "標準", "spec2": "", "price": product.get("price") or 0, "stock": 100, "image_url": main_images[0] if main_images else ""}]
    shipping_fee = safe_price(product.get("shipping_fee"))
    price_includes_shipping = bool(product.get("price_includes_shipping"))
    rows: list[list[Any]] = []
    for index, sku in enumerate(skus[:40]):
        first = index == 0
        sku_image = str(sku.get("image_url") or "")
        if is_public_asset_url(sku_image) or not is_importable_image_url(sku_image):
            sku_image = ""
        rows.append(
            [
                main_no,
                product.get("optimized_title", "") if first else "",
                "CNY" if first else "",
                images if first else "",
                product.get("offer_url", "") if first else "",
                "1688" if first else "",
                product.get("offer_id", "") if first else "",
                product.get("detail_description", "") if first else "",
                detail_images if first else "",
                product.get("category", "") if first else "",
                attrs if first else "",
                "",
                "",
                "",
                str(sku.get("spec1") or "標準"),
                str(sku.get("spec2") or ""),
                sku.get("platform_sku", ""),
                template_sku_price(sku.get("price") or product.get("price"), shipping_fee, price_includes_shipping),
                sku_image,
                int(float(sku.get("stock") or 100)),
                0.5,
                "10X10X40",
            ]
        )
    return rows


def dedupe_template_skus(skus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    used: set[str] = set()
    for sku in skus:
        raw_spec = str(sku.get("raw_spec1") or sku.get("original_spec") or sku.get("spec1") or "")
        spec1 = simplify_sku_name(str(sku.get("spec1") or "標準"))
        spec2 = simplify_sku_name(str(sku.get("spec2") or "")) if sku.get("spec2") else ""
        spec1, spec2 = unique_sku_specs(spec1, spec2, raw_spec, used)
        if not spec1:
            continue
        result.append(sku | {"spec1": spec1, "spec2": spec2})
    return result


def unique_sku_specs(spec1: str, spec2: str, raw_spec: str, used: set[str], target_language: str = "ja") -> tuple[str, str]:
    standard_sku = target_language_meta(target_language)["standard_sku"]
    spec1 = simplify_sku_name(spec1 or standard_sku, target_language)
    spec2 = simplify_sku_name(spec2 or "", target_language) if spec2 else ""
    key = sku_spec_combo_key(spec1, spec2)
    if key and key not in used:
        used.add(key)
        return spec1, spec2

    fallback = simplify_sku_name(raw_spec or "", target_language)
    if fallback and fallback != standard_sku:
        if sku_spec_combo_key(fallback, spec2) not in used:
            used.add(sku_spec_combo_key(fallback, spec2))
            return fallback, spec2
        if not spec2 and sku_spec_combo_key(spec1, fallback) not in used:
            used.add(sku_spec_combo_key(spec1, fallback))
            return spec1, fallback

    base = spec1 if spec1 else "SKU"
    for number in range(2, 100):
        candidate = f"{base}{number}"
        candidate_key = sku_spec_combo_key(candidate, spec2)
        if candidate_key not in used:
            used.add(candidate_key)
            return candidate, spec2
    return "", ""


def sku_spec_combo_key(spec1: str, spec2: str) -> str:
    return f"{clean_html_text(spec1).strip()}||{clean_html_text(spec2).strip()}"


def importable_image_urls(urls: list[str], limit: int) -> list[str]:
    return unique_urls([url for url in urls if is_importable_image_url(str(url))])[:limit]


def is_importable_image_url(url: str) -> bool:
    return bool(url and re.match(r"^https?://", url) and re.search(r"\.(jpg|jpeg|png|webp)(?:$|[?#])", url, re.IGNORECASE))


def is_public_asset_url(url: str) -> bool:
    return bool(url and url.startswith(DEFAULT_ASSET_BASE_URL.rstrip("/")))

def safe_price(value: Any) -> float:
    match = re.search(r"\d+(?:\.\d+)?", str(value or "0"))
    return float(match.group(0)) if match else 0.0


def price_with_shipping(price: Any, shipping_fee: Any) -> float:
    return round(safe_price(price) + safe_price(shipping_fee), 2)


def template_sku_price(price: Any, shipping_fee: Any, price_includes_shipping: bool) -> float:
    if price_includes_shipping:
        return round(safe_price(price), 2)
    return price_with_shipping(price, shipping_fee)


def write_rows_to_xls(output_path: Path, rows: list[list[Any]]) -> None:
    payload_path = output_path.with_suffix(".json")
    script_path = output_path.with_suffix(".ps1")
    payload_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    script_path.write_text(
        r'''
$ErrorActionPreference = "Stop"
$xlsPath = $args[0]
$jsonPath = $args[1]
$rows = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
$excel = $null
try {
  $excel = New-Object -ComObject Excel.Application
  $excel.Visible = $false
  $excel.DisplayAlerts = $false
  $wb = $excel.Workbooks.Open($xlsPath)
  $ws = $wb.Worksheets.Item(1)
  $ws.Range("A10:V500").ClearContents() | Out-Null
  $ws.Range("A10:A500").NumberFormat = "@"
  $ws.Range("G10:G500").NumberFormat = "@"
  $ws.Range("Q10:Q500").NumberFormat = "@"
  for ($r = 0; $r -lt $rows.Count; $r++) {
    $row = $rows[$r]
    for ($c = 0; $c -lt $row.Count; $c++) {
      $value = $row[$c]
      if ($null -eq $value) {
        $ws.Cells.Item(10 + $r, 1 + $c).Value2 = ""
      } elseif ($value -is [decimal] -or $value -is [int] -or $value -is [long] -or $value -is [double]) {
        $ws.Cells.Item(10 + $r, 1 + $c).Value2 = [double]$value
      } else {
        $ws.Cells.Item(10 + $r, 1 + $c).Value2 = [string]$value
      }
    }
  }
  $wb.Save()
  $wb.Close($true)
} finally {
  if ($excel) {
    $excel.Quit() | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
  }
}
'''.strip(),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), str(output_path), str(payload_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise AutoPublishError(f"写入妙手模板失败：{exc.stderr or exc.stdout}") from exc
    finally:
        for path in (payload_path, script_path):
            try:
                path.unlink()
            except OSError:
                pass


def _record_task(task: dict[str, Any]) -> None:
    task_id = str(task.get("task_id") or "")
    if task_id:
        task = task | {"api_usage": api_usage_for_task(task_id)}
    with TASK_HISTORY_LOCK:
        history = _read_json(HISTORY_FILE, [])
        if not isinstance(history, list):
            history = []
        history = [item for item in history if isinstance(item, dict) and item.get("task_id") != task.get("task_id")]
        history.insert(0, task)
        history = history[:50]
        _write_json(HISTORY_FILE, history)
        _write_json(LATEST_RESULT_FILE, task)






