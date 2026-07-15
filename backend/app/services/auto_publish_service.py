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
from typing import Any, Callable
from uuid import uuid4

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from urllib3.util.retry import Retry

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
DEFAULT_TEMPLATE_PATH = Path(os.getenv("MIAOSHOU_IMPORT_TEMPLATE", r"C:\Users\Gao\Downloads\导入产品模板 (1).xls"))
DEFAULT_OXYLABS_REALTIME_URL = "https://realtime.oxylabs.io/v1/queries"
BAIDU_PICTRANS_URL = "https://aip.baidubce.com/file/2.0/mt/pictrans/v1"
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_TOKEN_CACHE_FILE = RUNTIME_DIR / "baidu_pictrans_token.json"
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
DOUBAO_IMAGE_MODELS = ("doubao-seedream-5-0", "doubao-seedream-5-0-pro")
DOUBAO_IMAGE_ENDPOINTS = ("ep-20260710161912-qq7gf", "ep-20260710162015-r5rv9")
MAIN_IMAGE_SIZE = (1200, 1200)
DETAIL_IMAGE_WIDTH = 1200
SEEDREAM_REQUEST_SIZE = "1920x1920"
IMAGE_PROCESS_WORKERS = max(1, int(os.getenv("AUTO_PUBLISH_IMAGE_WORKERS", "4")))
MAIN_IMAGE_TARGET = 5
DETAIL_IMAGE_TARGET = 9
AI_IMAGE_TIMEOUT_SECONDS = max(30, int(os.getenv("AUTO_PUBLISH_AI_IMAGE_TIMEOUT", "75")))
MIAOSHOU_TASK_CREDENTIALS: dict[str, tuple[str, str]] = {}


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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


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


def get_latest_result() -> dict[str, Any]:
    return _read_json(
        LATEST_RESULT_FILE,
        {
            "ok": True,
            "status": "idle",
            "message": "尚未创建自动上架任务。",
            "steps": [],
            "errors": [],
            "product_infos": [],
        },
    )


def list_history() -> list[dict[str, Any]]:
    history = _read_json(HISTORY_FILE, [])
    if isinstance(history, list):
        return history
    return []


def get_task_result(task_id: str) -> dict[str, Any] | None:
    return next((item for item in list_history() if item.get("task_id") == task_id), None)


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
        "detail_limit": 9,
        "workers": min(max(IMAGE_PROCESS_WORKERS, 4), 6),
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
        raise ValueError("请填写妙手账号和密码。仅生成模板也需要登录妙手图片空间上传图片，本次输入不会保存。")

    task_id = uuid4().hex
    target_language = normalize_target_language(payload.get("target_language"))
    MIAOSHOU_TASK_CREDENTIALS[task_id] = (miaoshou_username, miaoshou_password)
    task = {
        "task_id": task_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "created_by": user_id,
        "status": "created",
        "workflow": "1688_to_miaoshou",
        "dry_run": bool(payload.get("dry_run", True)),
        "offer_url": offer_url,
        "image_mode": "smart",
        "publish_count": 1,
        "target_channel": "TikTok Shop Japan",
        "target_language": target_language,
        "erp_url": str(payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270"),
        "steps": [
            "已创建 1688 链接自动上架任务，等待执行。",
            "已接收本次妙手登录信息（不保存），用于验证码登录、图片空间上传和可选自动导入。",
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
    if task.get("workflow") != "1688_to_miaoshou":
        return run_task(task_id)

    steps: list[str] = []
    errors: list[str] = []
    offer_url = str(task.get("offer_url") or "")
    image_mode = normalize_image_mode(task.get("image_mode"))
    mode_settings = image_mode_settings(image_mode)
    main_target = int(mode_settings["main_target"])
    detail_target = int(mode_settings["detail_target"])
    update_task_progress(task_id, "fetch", 0, 1, "正在抓取1688数据", 5)
    try:
        raw_page = fetch_1688_page_with_oxylabs(db, offer_url)
        steps.append("已通过 Oxylabs 获取 1688 商品页数据。")
        update_task_progress(task_id, "fetch", 1, 1, "已获取1688商品数据", 18)
    except AutoPublishError as exc:
        raw_page = {"html": "", "raw": {}, "error": str(exc)}
        errors.append(str(exc))

    product = extract_1688_product(offer_url, raw_page.get("html", ""), raw_page.get("raw", {}))
    if product.get("title"):
        steps.append(f"已解析 1688 商品：{product['title']}")
    else:
        errors.append("未能从 1688 页面解析到商品标题。")

    update_task_progress(task_id, "copy", 0, 1, "正在优化标题/SKU/描述", 24)
    ensure_miaoshou_login_state(db, task["task_id"], str(task.get("erp_url") or ""))

    optimized = optimize_for_japan_listing(
        db,
        product,
        task["task_id"],
        image_mode=image_mode,
        progress_callback=lambda current, total: update_task_progress(
            task_id,
            "images",
            current,
            total,
            f"正在生成图片 {current}/{total}",
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
    update_task_progress(task_id, "template", 0, 1, "正在生成妙手模板", 84)
    steps.append("已完成标题、SKU 和商品描述优化。")
    if optimized.get("image_notice"):
        steps.append(str(optimized["image_notice"]))
    image_result = optimized.get("image_result") if isinstance(optimized.get("image_result"), dict) else {}
    image_ready = len(optimized.get("clean_main_images") or []) >= main_target and len(optimized.get("clean_detail_images") or []) >= detail_target
    if not image_ready:
        errors.append(
            f"图片数量不足：主图 {len(optimized.get('clean_main_images') or [])}/{main_target}，"
            f"详情图 {len(optimized.get('clean_detail_images') or [])}/{detail_target}。"
        )
        errors.extend(str(error) for error in (image_result.get("errors") or [])[:8])

    output_path = build_miaoshou_import_xls(task["task_id"], optimized)
    update_task_progress(task_id, "template", 1, 1, "妙手模板已生成", 88)
    steps.append(f"已按妙手导入模板生成文件：{output_path.name}")

    import_result: dict[str, Any] | None = None
    if task.get("dry_run", True):
        status = "template_ready"
        ok = True
        message = "妙手导入模板已生成。当前为 dry-run，未自动提交到公用采集箱。"
        steps.append("当前为 dry-run 模式：请在妙手后台手动导入生成的模板进行验证。")
    elif not image_ready:
        status = "template_ready"
        ok = False
        message = "模板已生成，但图片未达到自动导入要求，已停止导入妙手。"
        steps.append("图片未达到最低数量要求：已停止自动导入，避免不完整商品进入公用采集箱。")
    else:
        update_task_progress(task_id, "miaoshou", 0, 1, "正在导入妙手公用采集箱", 92)
        import_result = import_template_to_miaoshou(db, Path(output_path), str(task.get("erp_url") or ""), task_id=task_id)
        steps.extend(import_result.get("steps", []))
        errors.extend(import_result.get("errors", []))
        ok = bool(import_result.get("ok")) and not any("Oxylabs" in error for error in errors)
        status = "imported" if import_result.get("ok") else "import_failed"
        message = "已生成妙手模板并导入公用采集箱。" if import_result.get("ok") else "模板已生成，但自动导入妙手失败，请查看错误和截图。"

    result = task | {
        "status": status,
        "ok": ok and not any("Oxylabs" in error for error in errors),
        "message": message if not errors else f"{message} 但存在需要复核的问题。",
        "finished_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "steps": steps,
        "errors": errors,
        "product_infos": [optimized],
        "template_path": str(output_path),
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
    return result


class AutoPublishError(RuntimeError):
    pass


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
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(ThirdPartyConfig.service_type == "oxylabs", ThirdPartyConfig.status == 1)
        .order_by(ThirdPartyConfig.id.desc())
    )
    username = os.getenv("OXYLABS_USERNAME", "")
    password = os.getenv("OXYLABS_PASSWORD", "")
    endpoint = os.getenv("OXYLABS_REALTIME_URL", DEFAULT_OXYLABS_REALTIME_URL)
    if config:
        username = config.access_key_encrypted or username
        password = config.secret_key_encrypted or password
        endpoint = config.api_base_url or endpoint
    if not username or not password:
        raise AutoPublishError("Oxylabs 账号未配置：请在第三方 API 配置 oxylabs，或设置 OXYLABS_USERNAME/OXYLABS_PASSWORD。")
    return username, password, endpoint.rstrip("/")


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


def ensure_miaoshou_login_state(db: Session, task_id: str, erp_url: str) -> None:
    username, password = get_miaoshou_credentials(db, task_id)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AutoPublishError(f"Playwright 未安装，无法登录妙手上传图片：{exc}") from exc

    headless = os.getenv("MIAOSHOU_HEADLESS", "0") != "0"
    target_url = erp_url or "https://erp.91miaoshou.com/?ac=1og270"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(**browser_launch_options(headless))
        except Exception as exc:  # noqa: BLE001
            raise AutoPublishError(f"妙手浏览器启动失败：{exc}") from exc
        context_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
        if MIAOSHOU_STORAGE_STATE_PATH.exists():
            context_kwargs["storage_state"] = str(MIAOSHOU_STORAGE_STATE_PATH)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            close_miaoshou_popups(page)
            login_miaoshou(page, username, password)
            page.wait_for_timeout(1200)
            close_miaoshou_popups(page)
            if not is_miaoshou_logged_in(page):
                raise AutoPublishError("妙手登录未完成：请在弹出的浏览器中输入验证码并点击立即登录。")
            context.storage_state(path=str(MIAOSHOU_STORAGE_STATE_PATH))
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


def import_template_to_miaoshou(db: Session, template_path: Path, erp_url: str) -> dict[str, Any]:
    steps: list[str] = []
    errors: list[str] = []
    screenshots: list[str] = []
    try:
        username, password = get_miaoshou_credentials(db)
    except AutoPublishError as exc:
        return {"ok": False, "steps": [], "errors": [str(exc)], "screenshots": []}

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"ok": False, "steps": [], "errors": [f"Playwright 未安装：{exc}"], "screenshots": []}

    headless = os.getenv("MIAOSHOU_HEADLESS", "0") != "0"
    target_url = erp_url or "https://erp.91miaoshou.com/?ac=1og270"
    storage_path = RUNTIME_DIR / "miaoshou_storage_state.json"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(**browser_launch_options(headless))
        except Exception as exc:  # noqa: BLE001 - surface browser setup as a normal import failure.
            return {"ok": False, "steps": steps, "errors": [f"妙手浏览器启动失败：{exc}"], "screenshots": []}
        context_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
        if storage_path.exists():
            context_kwargs["storage_state"] = str(storage_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            steps.append(f"已打开妙手 ERP：{target_url}")
            close_miaoshou_popups(page)
            login_miaoshou(page, username, password)
            page.wait_for_timeout(2000)
            close_miaoshou_popups(page)
            if not is_miaoshou_logged_in(page):
                raise AutoPublishError("妙手登录未完成：请在弹出的浏览器中输入验证码并点击立即登录。")
            context.storage_state(path=str(storage_path))
            steps.append("已登录妙手并保存登录态。")
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


def login_miaoshou(page: Any, username: str, password: str) -> None:
    if is_miaoshou_logged_in(page):
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


def fetch_1688_page_with_oxylabs(db: Session, offer_url: str) -> dict[str, Any]:
    username, password, endpoint = get_oxylabs_config(db)
    payload = {
        "source": "universal",
        "url": offer_url,
        "geo_location": "China",
        "render": "html",
        "parse": False,
    }
    try:
        response = requests.post(endpoint, auth=(username, password), json=payload, timeout=90)
        if response.status_code >= 400:
            raise AutoPublishError(f"Oxylabs 请求失败：HTTP {response.status_code} {response.text[:300]}")
        data = response.json()
    except requests.RequestException as exc:
        data = post_oxylabs_with_powershell(endpoint, username, password, payload, str(exc))
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
    detail_images = [url for url in detail_images if normalize_image_url(url) not in sku_image_urls][:12]
    if not detail_images:
        detail_images = [url for url in image_urls if normalize_image_url(url) not in set(main_images) | sku_image_urls][:12]
    return {
        "offer_url": offer_url,
        "offer_id": offer_id,
        "title": title,
        "currency": "CNY",
        "price": price or "0",
        "shipping_fee": shipping_fee,
        "category": category,
        "main_images": main_images,
        "detail_images": detail_images[:12],
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
    return main_images, unique_urls(detail_candidates)[:12]


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
        r"品牌|产地|货号|加工定制|货源类型|是否跨境货源|主要下游平台|主要销售地区|"
        r"有可授权的自有品牌|有可授权的自由品牌|是否跨境出口专供货源|专利类型|"
        r"上市时间|上市年份|季节|价格段|专利|进出口|进口|出口|"
        r"跨境风格类型|主要下游销售地区"
    )
    result: dict[str, str] = {}
    value_set = {clean_html_text(str(value)) for value in properties.values()}
    for key, value in properties.items():
        raw_key = clean_html_text(str(key))
        raw_value = clean_html_text(str(value))
        if re.search(skip_key_pattern, raw_key):
            continue
        clean_key = raw_key
        clean_value = raw_value
        if not clean_key or not clean_value:
            continue
        if clean_key in value_set:
            continue
        if re.search(skip_key_pattern, clean_key):
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
    values = list(dict.fromkeys(values))[:12]
    if not values:
        return []
    return [
        {
            "spec1": simplify_sku_name(value),
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

    for key in ("shippingServices", "logisticsModel", "freightTemplate", "freightInfo", "deliveryInfo"):
        shipping = extract_json_object_after_key(html, key)
        fee = first_shipping_fee_from_object(shipping)
        if fee > 0:
            return fee
    if re.search(r"(?:运费|邮费|配送费)[^。；，,]{0,12}(?:包邮|免运费|免邮|free\s*shipping)", html, re.IGNORECASE):
        return 0.0

    patterns = [
        r"(?:运费|快递|物流|配送费|邮费)[^0-9¥￥]{0,20}[¥￥]?\s*(\d+(?:\.\d+)?)",
        r"[¥￥]\s*(\d+(?:\.\d+)?)[^。；，,]{0,12}(?:运费|快递|物流|配送费|邮费)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            fee = safe_price(match.group(1))
            if 0 < fee < 1000:
                return fee
    return 0.0


def first_shipping_fee_from_object(value: Any) -> float:
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
        "totalCost",
    }
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key in fee_keys:
                    fee = safe_price(child)
                    if 0 < fee < 1000:
                        return fee
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return 0.0


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
        spec1 = simplify_sku_name(spec_parts[0])
        spec2 = simplify_sku_name(spec_parts[1]) if len(spec_parts) > 1 else ""
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
            spec_name = simplify_sku_name(clean_html_text(raw_name))
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
        spec_name = simplify_sku_name(clean_html_text(str(raw_name)))
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
    if display_price:
        return display_price
    if isinstance(info, dict):
        for key in ("price", "salePrice", "offerPrice", "originalPrice", "discountPrice"):
            value = info.get(key)
            if value not in (None, ""):
                return str(value)
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

def simplify_sku_name(value: str) -> str:
    value = sanitize_listing_copy(value or "")
    value = re.sub(r"[\[\]【】()（）]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value or is_bad_sku_name(value):
        return "標準"
    value = translate_common_sku_name(value)
    return value[:24]


def translate_common_sku_name(value: str) -> str:
    replacements = {
        "小号": "小サイズ",
        "中号": "中サイズ",
        "大号": "大サイズ",
        "三层": "3段",
        "四层": "4段",
        "五层": "5段",
        "星星款": "スター",
        "苹果款": "アップル",
        "星星": "スター",
        "苹果": "アップル",
        "默认": "標準",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"\s+", " ", value).strip()

def prepare_compliant_images(
    task_id: str,
    product: dict[str, Any],
    image_mode: str = "fast",
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
    detail_source_urls = [url for url in unique_urls(product.get("detail_images", []) or []) if url not in main_source_set][:detail_limit]
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
    progress_state = {"done": 0, "total": 1}

    def set_progress_total(total: int) -> None:
        progress_state["total"] = max(1, total)

    def bump_progress() -> None:
        progress_state["done"] = min(progress_state["done"] + 1, progress_state["total"])
        if progress_callback:
            progress_callback(progress_state["done"], progress_state["total"])

    def add_processed(key: str, path: Path, role: str, sku_key: str = "") -> None:
        signature = image_signature(path)
        role_signatures = image_signatures.setdefault(role, [])
        comparison_signatures = role_signatures if role == "sku" else image_signatures.setdefault("all", [])
        if signature is not None and any(image_signature_distance(signature, old) <= 5 for old in comparison_signatures):
            errors.append(f"已跳过重复{role_image_label(role)}：{path.name}")
            return
        if signature is not None:
            role_signatures.append(signature)
            if role != "sku":
                image_signatures.setdefault("all", []).append(signature)
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
        )
        return {**job, "result": result}

    def run_image_jobs(jobs: list[dict[str, Any]], label: str) -> None:
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
                        errors.append(f"已删除不适合上架的{label}：{process_result.get('reason') or image_url}")
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
                    bump_progress()

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
    run_image_jobs(main_jobs, "主图")

    reference_path = next((item["path"] for item in processed_items if item["role"] == "main"), None)
    if len(main_keys) < main_target:
        errors.append(f"主图可用数量 {len(main_keys)}/{main_target}，按要求不再自动生成补图。")

    detail_jobs = [
        {"key": image_url, "source_url": image_url, "path": local_dir / f"detail_{index:02d}.jpg", "role": "detail", "index": index}
        for index, image_url in enumerate(detail_source_urls[:detail_limit], start=1)
    ]
    run_image_jobs(detail_jobs, "详情图")

    if len(detail_keys) < detail_target:
        errors.append(f"详情图可用数量 {len(detail_keys)}/{detail_target}，按要求不再自动生成补图。")

    run_image_jobs(sku_jobs, "SKU图")

    for _index, sku_key in missing_sku_items:
        errors.append(f"SKU `{sku_key}` 没有原始图片，按要求不再自动生成补图。")

    main_order = {url: index for index, url in enumerate(main_source_urls)}
    detail_order = {url: index for index, url in enumerate(detail_source_urls)}
    main_fallback_order = {key: index for index, key in enumerate(list(main_keys))}
    detail_fallback_order = {key: index for index, key in enumerate(list(detail_keys))}
    main_keys.sort(key=lambda key: main_order.get(key, 1000 + main_fallback_order.get(key, 0)))
    detail_keys.sort(key=lambda key: detail_order.get(key, 1000 + detail_fallback_order.get(key, 0)))

    processed_paths = [item["path"] for item in processed_items]
    if processed_paths:
        try:
            if status_callback:
                status_callback("正在上传图片到妙手图片空间", 81)
            uploaded_map = upload_images_to_miaoshou_picture_space(processed_paths)
            for item in processed_items:
                if item["path"] in uploaded_map:
                    url_map[item["key"]] = uploaded_map[item["path"]]
        except AutoPublishError as exc:
            errors.append(str(exc))
            try:
                if status_callback:
                    status_callback("妙手图片空间上传失败，正在回退上传到公网", 82)
                upload_images_to_ecs(task_id, processed_paths)
                for item in processed_items:
                    url_map[item["key"]] = f"{DEFAULT_ASSET_BASE_URL.rstrip('/')}/{task_id}/{item['path'].name}"
            except AutoPublishError as ecs_exc:
                errors.append(str(ecs_exc))
                url_map = {}
    main_images = [url_map[key] for key in main_keys if key in url_map][:main_target]
    detail_images = [url_map[key] for key in detail_keys if key in url_map][:detail_target]
    sku_image_map = {sku_key: url_map[key] for sku_key, key in sku_keys.items() if key in url_map}
    notice = (
        f"图片已按角色处理并上传妙手图片空间：主图 {len(main_images)} 张，详情图 {len(detail_images)} 张，SKU图 {len(sku_image_map)} 张。"
        "含中文图片已尝试用 AI MediaKit 翻译，风险元素已尝试擦除；按当前规则不再自动生成补图，仍建议抽检。"
        if url_map
        else "图片处理或上传失败，模板将回退使用原图链接，请人工复核。"
    )
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

    if not likely_contains_product(image):
        return {"keep": False, "reason": "图片过小或比例异常，疑似不包含商品主体。"}
    if role == "detail":
        promo_reason = detect_supply_chain_promo_image(image, product)
        if promo_reason:
            return {"keep": False, "reason": promo_reason, "editor": "promo_filter"}
    if not use_seedream:
        return process_image_low_cost(image, output_path, product, role=role, sku_text=sku_text)
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

    if analysis.get("keep") is False:
        return {"keep": False, "reason": str(analysis.get("reason") or "视觉模型判断不适合上架。")}
    if requires_ai_regeneration(analysis):
        reason = "图片含中文/人脸/Logo/水印等风险区域，Seedream 未成功生成合规新图，已丢弃，避免色块修补图进入妙手。"
        if seedream_result.get("error"):
            reason = f"{reason} {seedream_result['error']}"
        return {"keep": False, "reason": reason, "analysis": analysis, "editor": "discarded"}
    if seedream_result.get("error") and not analysis:
        return {
            "keep": False,
            "reason": f"Seedream 未成功生成参考新图，且视觉分析不可用，已丢弃原图避免风险图进入妙手。{seedream_result['error']}",
            "analysis": analysis,
            "editor": "discarded",
        }
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
                response = session.get(candidate, timeout=(12, 35), headers=headers)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not response.content or (content_type and "image" not in content_type):
                    raise requests.RequestException(f"返回内容不是图片：{content_type or 'unknown'}")
                return response.content
            except requests.RequestException as exc:
                errors.append(f"{candidate}: {exc}")
    raise requests.RequestException("；".join(errors[-3:]) or image_url)


def translate_detail_image_with_aimediakit(image: Image.Image, output_path: Path, role: str = "detail") -> dict[str, Any]:
    config = get_default_model_config_for_translation()
    if not config or not config.api_key_encrypted:
        return {"ok": False, "error": "AI MediaKit 图片翻译未配置：请配置 Doubao-Seed-Translation API Key。"}
    endpoint = config.base_url or AIMEDIAKIT_IMAGE_TRANSLATE_URL
    image_data_url = image_to_data_url_for_mediakit(image)
    payload = {"image_url": image_data_url, "target_lang": "ja"}
    try:
        payload = post_aimediakit_tool(endpoint, config.api_key_encrypted, payload)
    except requests.RequestException as exc:
        return {"ok": False, "error": f"AI MediaKit 图片翻译请求失败：{sanitize_secret_error(str(exc))}"}

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
        return {"ok": True, "editor": "aimediakit_seed_translation"}
    except (OSError, ValueError, UnidentifiedImageError, requests.RequestException) as exc:
        return {"ok": False, "error": f"AI MediaKit 图片翻译返回图片无法识别：{exc}"}


def remove_image_elements_with_aimediakit(image: Image.Image, output_path: Path, role: str = "main") -> dict[str, Any]:
    config = get_default_model_config_for_translation()
    if not config or not config.api_key_encrypted:
        return {"ok": False, "error": "AI MediaKit 未配置。"}
    image_data_url = image_to_data_url_for_mediakit(image)
    try:
        payload = post_aimediakit_tool(
            AIMEDIAKIT_REMOVE_ELEMENTS_URL,
            config.api_key_encrypted,
            {"image_url": image_data_url},
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"AI MediaKit 牛皮癣擦除请求失败：{sanitize_secret_error(str(exc))}"}
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


def post_aimediakit_tool(endpoint: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=(12, 120),
    )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise requests.RequestException(f"HTTP {response.status_code} {response.text[:500]}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise requests.RequestException(f"返回不是JSON：{response.text[:500]}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise requests.RequestException(json.dumps(data, ensure_ascii=False)[:500])
    return data if isinstance(data, dict) else {"data": data}


def image_to_data_url_for_mediakit(image: Image.Image) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_translation_request_bytes(image)).decode("ascii")


def image_translation_request_bytes(image: Image.Image) -> bytes:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    longest = max(prepared.size)
    if longest > 2048:
        ratio = 2048 / longest
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
    response = requests.get(
        image_url,
        headers={"User-Agent": "Mozilla/5.0 TKAutoPublish/1.0", "Accept": "image/*,*/*;q=0.8"},
        timeout=(12, 60),
    )
    response.raise_for_status()
    if not response.content:
        raise requests.RequestException("empty image response")
    return response.content


def translate_detail_image_with_baidu(image: Image.Image, output_path: Path, role: str = "detail") -> dict[str, Any]:
    config = get_baidu_pictrans_config()
    if not config.get("api_key") or not config.get("secret_key"):
        return {"ok": False, "error": "百度图片翻译未配置：请新增第三方API service_type=baidu_pictrans，或设置 BAIDU_PICTRANS_API_KEY/BAIDU_PICTRANS_SECRET_KEY。"}
    try:
        token = get_baidu_access_token(str(config["api_key"]), str(config["secret_key"]))
        image_bytes = baidu_pictrans_request_bytes(image)
        response = requests.post(
            str(config.get("api_base_url") or BAIDU_PICTRANS_URL),
            params={"access_token": token},
            data={"from": "zh", "to": "jp", "v": "3", "paste": "1"},
            files={"image": ("detail.jpg", image_bytes, "image/jpeg")},
            timeout=(10, 60),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, OSError) as exc:
        return {"ok": False, "error": f"百度图片翻译请求失败：{exc}"}

    error_code = str(payload.get("error_code", "0"))
    if error_code not in {"0", ""}:
        error_msg = str(payload.get("error_msg") or "")
        if error_code in {"69003", "69004"}:
            return {"ok": False, "skip": True, "reason": f"百度图片翻译未识别到可翻译文字：{error_msg or error_code}"}
        return {"ok": False, "error": f"百度图片翻译失败：{error_code} {error_msg}".strip()}

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    pasted = data.get("pasteImg") if isinstance(data, dict) else ""
    if not isinstance(pasted, str) or not pasted:
        return {"ok": False, "skip": True, "reason": "百度图片翻译未返回整图贴合结果。"}
    try:
        translated = Image.open(BytesIO(base64.b64decode(pasted))).convert("RGBA")
        save_standard_product_image(translated, output_path, role=role, quality=92)
        return {"ok": True, "translated_text": data.get("sumDst") if isinstance(data, dict) else ""}
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        return {"ok": False, "error": f"百度图片翻译返回图片无法识别：{exc}"}


def baidu_pictrans_request_bytes(image: Image.Image) -> bytes:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    width, height = prepared.size
    if width <= 0 or height <= 0:
        raise OSError("图片尺寸异常")
    if height / width > 3:
        target_width = int(height / 3) + 2
        canvas = Image.new("RGB", (target_width, height), (246, 246, 244))
        canvas.paste(prepared, ((target_width - width) // 2, 0))
        prepared = canvas
    elif width / height > 3:
        target_height = int(width / 3) + 2
        canvas = Image.new("RGB", (width, target_height), (246, 246, 244))
        canvas.paste(prepared, (0, (target_height - height) // 2))
        prepared = canvas
    longest = max(prepared.size)
    if longest > 4096:
        ratio = 4096 / longest
        prepared = prepared.resize((max(30, int(prepared.width * ratio)), max(30, int(prepared.height * ratio))), Image.Resampling.LANCZOS)
    shortest = min(prepared.size)
    if shortest < 30:
        ratio = 30 / max(shortest, 1)
        prepared = prepared.resize((int(prepared.width * ratio), int(prepared.height * ratio)), Image.Resampling.LANCZOS)
    for quality in (90, 84, 78, 72, 66):
        buffer = BytesIO()
        prepared.save(buffer, "JPEG", quality=quality, optimize=True)
        if buffer.tell() <= 4 * 1024 * 1024:
            return buffer.getvalue()
    raise OSError("图片压缩后仍超过百度图片翻译4MB限制")


def get_baidu_pictrans_config() -> dict[str, str]:
    api_key = os.getenv("BAIDU_PICTRANS_API_KEY", "") or os.getenv("BAIDU_API_KEY", "")
    secret_key = os.getenv("BAIDU_PICTRANS_SECRET_KEY", "") or os.getenv("BAIDU_SECRET_KEY", "")
    api_base_url = os.getenv("BAIDU_PICTRANS_URL", BAIDU_PICTRANS_URL)
    try:
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            config = db.scalar(
                select(ThirdPartyConfig)
                .where(
                    ThirdPartyConfig.service_type.in_(("baidu_pictrans", "baidu_image_translate", "baidu_mt")),
                    ThirdPartyConfig.status == 1,
                )
                .order_by(ThirdPartyConfig.id.desc())
            )
        finally:
            db.close()
        if config:
            api_key = config.access_key_encrypted or api_key
            secret_key = config.secret_key_encrypted or secret_key
            api_base_url = config.api_base_url or api_base_url
    except Exception:
        pass
    return {"api_key": api_key, "secret_key": secret_key, "api_base_url": api_base_url or BAIDU_PICTRANS_URL}


def get_baidu_access_token(api_key: str, secret_key: str) -> str:
    _ensure_runtime_dir()
    cache_key = hashlib.sha256(f"{api_key}:{secret_key}".encode("utf-8")).hexdigest()
    cache = _read_json(BAIDU_TOKEN_CACHE_FILE, {})
    cached = cache.get(cache_key) if isinstance(cache, dict) else None
    if isinstance(cached, dict) and cached.get("access_token") and float(cached.get("expires_at") or 0) > time.time() + 600:
        return str(cached["access_token"])
    try:
        response = requests.post(
            BAIDU_TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": api_key, "client_secret": secret_key},
            headers={"Accept": "application/json"},
            timeout=(8, 30),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        payload = get_baidu_access_token_with_powershell(api_key, secret_key, str(exc))
    token = payload.get("access_token")
    if not token:
        raise requests.RequestException(str(payload.get("error_description") or payload.get("error") or "百度access_token获取失败"))
    expires_in = int(payload.get("expires_in") or 2592000)
    if not isinstance(cache, dict):
        cache = {}
    cache[cache_key] = {"access_token": token, "expires_at": time.time() + max(3600, expires_in - 3600)}
    _write_json(BAIDU_TOKEN_CACHE_FILE, cache)
    return str(token)


def get_baidu_access_token_with_powershell(api_key: str, secret_key: str, original_error: str) -> dict[str, Any]:
    _ensure_runtime_dir()
    temp_prefix = RUNTIME_DIR / f"baidu_token_{uuid4().hex}"
    response_path = temp_prefix.with_suffix(".json")
    error_path = temp_prefix.with_suffix(".error.txt")
    script_path = temp_prefix.with_suffix(".ps1")
    script_path.write_text(
        f'''
$ErrorActionPreference = "Stop"
$uri = "{BAIDU_TOKEN_URL}"
$body = @{{
  grant_type = "client_credentials"
  client_id = "{escape_powershell_string(api_key)}"
  client_secret = "{escape_powershell_string(secret_key)}"
}}
try {{
  $response = Invoke-RestMethod -Method Post -Uri $uri -Body $body -TimeoutSec 30
  $response | ConvertTo-Json -Depth 8 | Set-Content -Path "{response_path}" -Encoding UTF8
}} catch {{
  $_.Exception.Message | Set-Content -Path "{error_path}" -Encoding UTF8
  exit 1
}}
'''.strip(),
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if completed.returncode != 0 or not response_path.exists():
            ps_error = error_path.read_text(encoding="utf-8", errors="ignore").strip() if error_path.exists() else completed.stderr.strip()
            raise requests.RequestException(f"百度access_token获取失败：Python请求SSL失败，PowerShell兜底也失败：{ps_error or 'unknown'}")
        return json.loads(response_path.read_text(encoding="utf-8-sig"))
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
        raise requests.RequestException(f"百度access_token获取失败：{sanitize_secret_error(original_error)}；PowerShell兜底异常：{exc}") from exc
    finally:
        for path in (script_path, response_path, error_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def escape_powershell_string(value: str) -> str:
    return str(value).replace("`", "``").replace('"', '`"')


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
) -> dict[str, Any]:
    analysis = analyze_image_low_cost(image, product)
    if analysis.get("keep") is False:
        return {"keep": False, "reason": str(analysis.get("reason") or "视觉模型判断不适合上架。"), "analysis": analysis}
    if analysis_has_cjk_text(analysis):
        translation_result = translate_detail_image_with_aimediakit(image, output_path, role=role)
        if translation_result.get("ok"):
            return {"keep": True, "analysis": analysis, "editor": "aimediakit_seed_translation"}
        if translation_result.get("skip"):
            save_standard_product_image(image, output_path, role=role, quality=90)
            return {"keep": True, "analysis": analysis, "editor": "aimediakit_skip"}
        return {
            "keep": False,
            "reason": f"图片含中文但 AI MediaKit 图片翻译失败，已丢弃避免原中文进入模板。{translation_result.get('error') or ''}",
            "analysis": analysis,
            "editor": "discarded",
        }
    if has_blocking_visual_risk(analysis):
        remove_result = remove_image_elements_with_aimediakit(image, output_path, role=role)
        if remove_result.get("ok"):
            return {"keep": True, "analysis": analysis, "editor": "aimediakit_remove_elements"}
        return {
            "keep": False,
            "reason": f"图片含人脸、Logo、水印、二维码或联系方式等风险元素，AI MediaKit 牛皮癣擦除失败后已丢弃。{remove_result.get('error') or ''}",
            "analysis": analysis,
            "editor": "discarded_risk",
        }
    save_standard_product_image(image, output_path, role=role, quality=90)
    return {"keep": True, "analysis": analysis, "editor": "original_clean"}


def analyze_image_low_cost(image: Image.Image, product: dict[str, Any]) -> dict[str, Any]:
    config = get_default_model_config_for_images()
    if not config:
        return {"keep": True, "has_cjk_text": True, "risk": False, "reason": "视觉模型未配置，保守走 AI MediaKit 图片翻译。"}
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=560)).decode("ascii")
    instruction = (
        "快速判断1688商品图，低成本输出JSON。"
        "字段：keep=是否包含商品主体且不是纯广告/工厂/二维码/联系方式图；"
        "has_cjk_text=画面是否有中文汉字；"
        "risk=是否有人脸、品牌Logo、水印、二维码、联系方式、明显侵权IP或平台标识；"
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
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", str(content), re.DOTALL)
        parsed = json.loads(match.group(0) if match else str(content))
        if not isinstance(parsed, dict):
            return {}
        return normalize_low_cost_analysis(parsed)
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return {"keep": True, "has_cjk_text": True, "risk": False, "reason": "快速图片判断失败，保守走 AI MediaKit 图片翻译。"}


def normalize_low_cost_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(parsed)
    has_cjk = bool(analysis.get("has_cjk_text") or analysis.get("has_chinese") or analysis.get("contains_chinese"))
    risk = bool(analysis.get("risk") or analysis.get("has_risk"))
    if has_cjk:
        analysis["text_regions"] = [{"source_text": "中文"}]
    else:
        analysis["text_regions"] = []
    if risk:
        analysis["remove_regions"] = [{"reason": clean_html_text(str(analysis.get("reason") or "risk"))}]
    else:
        analysis["remove_regions"] = []
    analysis["keep"] = bool(analysis.get("keep", True))
    return analysis


def analysis_has_cjk_text(analysis: dict[str, Any]) -> bool:
    for item in (analysis.get("text_regions") or []):
        if not isinstance(item, dict):
            continue
        text = clean_html_text(str(item.get("source_text") or ""))
        if contains_cjk(text):
            return True
    return False


def has_blocking_visual_risk(analysis: dict[str, Any]) -> bool:
    if analysis.get("risk") is True or analysis.get("has_risk") is True:
        return True
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
        "watermark",
        "水印",
        "qr",
        "二维码",
        "contact",
        "联系方式",
        "店铺",
        "平台标识",
        "ip",
        "侵权",
    )
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


def detect_supply_chain_promo_image(image: Image.Image, product: dict[str, Any]) -> str:
    config = get_default_model_config_for_images()
    if not config:
        return ""
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_to_jpeg_bytes(image, max_size=560)).decode("ascii")
    instruction = (
        "判断这张1688商品详情图片是否属于应直接删除的供应链宣传图。"
        "以下任一内容占主要画面就删除：一件代发、厂家实力、源头工厂、工厂介绍、厂房、生产车间、流水线、仓库、"
        "团队合影、企业资质、招商加盟、代理招募、批发政策、发货流程、售后承诺、店铺宣传、联系方式、二维码。"
        "正常商品主体图、商品细节图、尺寸图、材质图、使用说明图、真实使用场景图不要删除。"
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
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", str(content), re.DOTALL)
        parsed = json.loads(match.group(0) if match else str(content))
        if isinstance(parsed, dict) and parsed.get("delete") is True:
            reason = clean_html_text(str(parsed.get("reason") or "供应链/工厂宣传图"))
            return f"已跳过供应链宣传图：{reason}"
    except (requests.RequestException, ValueError, json.JSONDecodeError):
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
            "判断图片是否包含商品主体，不包含商品主体则 keep=false",
            "识别图片中的中文文字区域，并翻译为自然日语",
            "即使图片包含大面积营销文案、参数说明、承重/尺寸/卖点文字，也不要因此删除图片；应返回文字区域给后续图生图原位替换。",
            "只有图片不包含商品主体、纯店铺广告、二维码/联系方式占主导、人物或明显侵权IP占主导时，才 keep=false。",
            "识别需要抹除的侵权/风险信息：Logo、品牌、二维码、联系方式、水印、店铺名、平台标识、动漫/IP、人物脸部",
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
        return select_auto_publish_model_config(db, "image_text_translation")
    finally:
        db.close()


def get_default_model_config_for_images() -> ModelConfig | None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return select_auto_publish_model_config(db, "image_analysis")
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
    background = ImageOps.fit(image.convert("RGB"), MAIN_IMAGE_SIZE, method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(18))
    background = ImageEnhance.Brightness(background).enhance(1.08)
    background = ImageEnhance.Contrast(background).enhance(0.92)
    overlay = Image.new("RGB", MAIN_IMAGE_SIZE, (245, 243, 238))
    canvas = Image.blend(background, overlay, 0.22)
    image.thumbnail(MAIN_IMAGE_SIZE, Image.Resampling.LANCZOS)
    left = (MAIN_IMAGE_SIZE[0] - image.width) // 2
    top = (MAIN_IMAGE_SIZE[1] - image.height) // 2
    canvas.paste(image.convert("RGB"), (left, top), image if image.mode == "RGBA" else None)
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
    background = ImageOps.fit(image.convert("RGB"), MAIN_IMAGE_SIZE, method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(18))
    background = ImageEnhance.Brightness(background).enhance(1.08)
    background = ImageEnhance.Contrast(background).enhance(0.92)
    overlay = Image.new("RGB", MAIN_IMAGE_SIZE, (245, 243, 238))
    canvas = Image.blend(background, overlay, 0.22)
    image.thumbnail((target_size[0], target_size[1] - caption_height), Image.Resampling.LANCZOS)
    left = (MAIN_IMAGE_SIZE[0] - image.width) // 2
    top = caption_height + ((MAIN_IMAGE_SIZE[1] - caption_height - image.height) // 2)
    canvas.paste(image.convert("RGB"), (left, top), image if image.mode == "RGBA" else None)
    if captions:
        draw_caption_band(canvas, captions, caption_height)
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.25)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.06)
    canvas = ImageEnhance.Color(canvas).enhance(1.04)
    return canvas


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


def upload_images_to_miaoshou_picture_space(image_paths: list[Path]) -> dict[Path, str]:
    if not MIAOSHOU_STORAGE_STATE_PATH.exists():
        raise AutoPublishError("妙手图片空间上传失败：缺少妙手登录态，请先完成一次妙手登录。")
    session = requests.Session()
    try:
        state = json.loads(MIAOSHOU_STORAGE_STATE_PATH.read_text(encoding="utf-8"))
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
        try:
            with image_path.open("rb") as file_obj:
                response = session.post(
                    MIAOSHOU_PICTURE_UPLOAD_URL,
                    data={"uploadType": "file", "scene": "product"},
                    files={"uploadImgFile": (image_path.name, file_obj, "image/jpeg")},
                    timeout=60,
                )
            response.raise_for_status()
            payload = response.json()
        except (OSError, requests.RequestException, ValueError) as exc:
            raise AutoPublishError(f"妙手图片空间上传失败：{image_path.name} {exc}") from exc
        if payload.get("result") != "success" or not payload.get("picturePath"):
            reason = payload.get("reason") or payload.get("message") or str(payload)[:200]
            raise AutoPublishError(f"妙手图片空间上传失败：{image_path.name} {reason}")
        uploaded[image_path] = str(payload["picturePath"])
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
    image_mode: str = "fast",
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    ai_result = call_listing_ai(db, product)
    title = ensure_japanese_title(ai_result.get("japanese_title") or "", product)
    description = ai_result.get("detail_description") or ai_result.get("description") or ""
    if not looks_like_japanese(description):
        description = build_description(product)
    description = sanitize_listing_copy(description)
    sku_map = ai_result.get("sku_names") if isinstance(ai_result.get("sku_names"), dict) else {}
    image_result = prepare_compliant_images(
        task_id,
        product,
        image_mode=image_mode,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
    image_map = image_result.get("url_map", {})
    original_main_images = unique_urls(product.get("main_images", []) or [])
    original_detail_images = unique_urls(product.get("detail_images", []) or [])
    main_images = importable_image_urls(image_result.get("main_images", []) or [], limit=MAIN_IMAGE_TARGET)
    detail_images = importable_image_urls(image_result.get("detail_images", []) or [], limit=DETAIL_IMAGE_TARGET)
    if not main_images:
        main_images = mapped_image_urls(original_main_images, image_map, limit=MAIN_IMAGE_TARGET)
    if not detail_images:
        detail_images = mapped_image_urls([url for url in original_detail_images if url not in set(original_main_images)], image_map, limit=DETAIL_IMAGE_TARGET)
    if not detail_images:
        detail_images = mapped_image_urls([url for url in original_detail_images if url not in original_main_images], image_map, limit=DETAIL_IMAGE_TARGET)
    sku_image_map = image_result.get("sku_image_map", {}) if isinstance(image_result.get("sku_image_map"), dict) else {}

    source_skus = [sku for sku in product.get("skus", []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
    if not source_skus:
        source_skus = [{"spec1": "標準", "spec2": "", "price": product.get("price") or "0", "stock": 100, "image_url": ""}]

    shipping_fee = safe_price(product.get("shipping_fee"))
    skus = []
    used_spec_keys: set[str] = set()
    for index, sku in enumerate(source_skus[:20], start=1):
        original_spec = str(sku.get("spec1") or "標準")
        spec1 = simplify_sku_name(str(sku_map.get(original_spec) or original_spec or "標準"))
        spec2 = simplify_sku_name(str(sku.get("spec2") or "")) if sku.get("spec2") else ""
        spec1, spec2 = unique_sku_specs(spec1, spec2, original_spec, used_spec_keys)
        if not spec1:
            continue
        original_image = normalize_image_url(str(sku.get("image_url") or ""))
        sku_image = sku_image_map.get(sku_identity(sku)) or image_map.get(original_image) or ""
        skus.append(
            sku
            | {
                "spec1": spec1,
                "spec2": spec2,
                "raw_spec1": original_spec,
                "raw_spec2": str(sku.get("spec2") or ""),
                "platform_sku": f"1688-{product.get('offer_id') or 'item'}-{index:03d}",
                "image_url": sku_image,
                "source_price": safe_price(sku.get("price") or product.get("price")),
                "price": price_with_shipping(sku.get("price") or product.get("price"), shipping_fee),
                "stock": int(float(sku.get("stock") or 100)),
            }
        )
    if not skus:
        skus = [{"spec1": "標準", "spec2": "", "price": price_with_shipping(product.get("price"), shipping_fee), "stock": 100, "image_url": ""}]
    return product | {
        "optimized_title": title[:120],
        "detail_description": description[:1800],
        "optimized_skus": skus,
        "clean_main_images": main_images,
        "clean_detail_images": detail_images,
        "image_notice": image_result.get("notice", "图片已完成基础合规处理。"),
        "image_result": image_result,
        "price_includes_shipping": True,
    }


def mapped_image_urls(source_urls: list[str], image_map: dict[str, str], limit: int) -> list[str]:
    mapped = []
    for url in source_urls:
        value = image_map.get(url)
        if value:
            mapped.append(value)
    return unique_urls(mapped)[:limit]

def call_listing_ai(db: Session, product: dict[str, Any]) -> dict[str, Any]:
    config = select_auto_publish_model_config(db, "listing_text")
    if not config or not config.api_key_encrypted or not config.base_url or not config.model_name:
        return {}
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    prompt = {
        "source_title": product.get("title"),
        "category": product.get("category"),
        "properties": product.get("properties"),
        "price_cny": product.get("price"),
        "sku_names": [item.get("spec1") for item in product.get("skus", [])[:30] if not is_bad_sku_name(str(item.get("spec1") or ""))],
        "target_market": "Japan / TikTok Shop Japan",
        "goal": "生成适合日本 TikTok Shop 跨境店的商品标题、详情描述和 SKU 名称。",
        "output_schema": {
            "japanese_title": "自然な日本語の商品タイトル",
            "detail_description": "日本語HTMLの商品説明",
            "sku_names": {"原SKU名": "短い日本語SKU名"},
        },
        "rules": [
            "标题必须是自然日语，符合日本当地购物搜索习惯，通顺但不过度堆词。",
            "不要出现 1688、阿里巴巴、厂家、爆款、新款、北欧风格、跨境、批发、源头、一件代发、现货等供应链词。",
            "不要出现侵权风险词：品牌名、IP角色名、动漫名、官方、正規品、专利、特許、専利、专利款、专利设计等。",
            "描述必须围绕商品本身特点，写成吸引日本消费者购买的自然销售文案，不要写成产品属性表。",
            "描述里不要输出 属性名:属性值 的列表，不要出现材质、产地、货号、平台、销售地区、是否跨境、货源类型等供应链字段。",
            "不得编造材质、认证、功效、适用人群、尺寸、配送时效或售后承诺。",
            "不要出现几天到、当日発送、翌日配送、最安、最高級、絶対、100%保証、爆売れ、必買等夸大或承诺文案。",
            "SKU 名称必须简短日语、清楚好懂，删除复杂冗余文字和专利相关词。",
            "只返回 JSON，不要解释。",
        ],
    }
    payload = {
        "model": config.model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "あなたは日本向けTikTok Shop越境店の商品編集者です。JSONのみ出力してください。"
                    "japanese_titleは日本の買い物検索習慣に合う自然で通順な日本語にしてください。"
                    "タイトル、説明、SKUには1688、阿里巴巴、メーカー直送、爆売れ、新作、北欧風、越境、卸売、仕入れ元、代行、即納などの供給側表現を含めない。"
                    "ブランド名、IP名、キャラクター名、公式、正規品、特許、専利、特許デザインなど権利侵害や専利リスクのある表現は禁止。"
                    "detail_descriptionは商品の実際の魅力を伝える日本語HTMLの販売文にし、属性表やスペック表を書かない。"
                    "材質、産地、品番、プラットフォーム、販売地域、越境、仕入れ、貨源など供給側フィールドを入れない。"
                    "未確認の材質、認証、効能、配送日数、誇大表現を作らない。"
                    "sku_namesは元SKU名から短く分かりやすい日本語SKU名へのマッピングにする。冗長語、複雑語、特許関連語を削除する。"
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
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        return parsed if isinstance(parsed, dict) else {}
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return {}


def select_auto_publish_model_config(db: Session, purpose: str) -> ModelConfig | None:
    configs = db.scalars(
        select(ModelConfig).where(ModelConfig.status == 1).order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
    ).all()
    if not configs:
        return None

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
        return with_key[0]
    fallback = [item for item in configs if item.api_key_encrypted and item.base_url and item.model_name and not is_seedream_model(item)]
    if fallback:
        return fallback[0]
    return preferred[0] if preferred else configs[0]


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
    if "auto_publish:image_text_translation" in value:
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
    title = sanitize_listing_copy(clean_html_text(title or ""))
    banned = banned_listing_pattern()
    if title and re.search(r"[ぁ-んァ-ヶー]", title) and not re.search(banned, title):
        return title
    return fallback_japanese_title(str(product.get("title") or ""))


def looks_like_japanese(value: str) -> bool:
    return bool(value and re.search(r"[ぁ-んァ-ヶー]", value))


def contains_cjk(value: str) -> bool:
    return bool(value and re.search(r"[\u4e00-\u9fff]", value))


def fallback_japanese_title(title: str) -> str:
    source = clean_html_text(title)
    lower = source.lower()
    if any(token in source for token in ("锅垫", "隔热垫", "防烫", "茶杯", "杯垫", "圣诞树", "树")):
        return "木製ツリー型鍋敷き 耐熱コースター キッチン雑貨 インテリア置物"
    if any(token in source for token in ("连衣裙", "裙", "女装")):
        return "レディースワンピース 上品デザイン きれいめ カジュアル おしゃれ"
    if any(token in source for token in ("奖状", "证书", "文件夹", "画册", "收纳")):
        return "賞状ファイル 証書収納ホルダー A4/A3対応 学生用 作品整理"
    if "pet" in lower or any(token in source for token in ("宠物", "猫", "狗")):
        return "ペット用品 便利グッズ お手入れしやすい 日常使い"
    return "便利グッズ 暮らしを整える実用アイテム"

def build_description(product: dict[str, Any]) -> str:
    title = ensure_japanese_title("", product)
    return (
        f"<p>{title}は、毎日のコーディネートや暮らしの中で使いやすさを感じられるアイテムです。</p>"
        "<p>シンプルに取り入れやすく、手持ちのアイテムとも合わせやすい雰囲気に仕上がっています。"
        "普段使いはもちろん、お出かけや気分を変えたい日にも自然になじみます。</p>"
        "<ul>"
        "<li>すっきり見えるデザインで、日常に取り入れやすい</li>"
        "<li>使うシーンを選びにくく、幅広いスタイルに合わせやすい</li>"
        "<li>見た目と使いやすさのバランスを重視したい方におすすめ</li>"
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


def miaoshou_rows(product: dict[str, Any]) -> list[list[Any]]:
    main_no = f"A{product.get('offer_id') or datetime.utcnow().strftime('%H%M%S')}"
    main_images = importable_image_urls(product.get("clean_main_images", []), limit=9)
    detail_image_list = importable_image_urls(product.get("clean_detail_images", []), limit=15)
    images = ",".join(main_images)
    detail_images = ",".join(detail_image_list)
    attrs = "；".join(f"{key}:{value}" for key, value in template_property_pairs(product.get("properties", {}) or {}).items())[:500]
    skus = [sku for sku in (product.get("optimized_skus") or product.get("skus") or []) if not is_bad_sku_name(str(sku.get("spec1") or ""))]
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


def unique_sku_specs(spec1: str, spec2: str, raw_spec: str, used: set[str]) -> tuple[str, str]:
    spec1 = simplify_sku_name(spec1 or "標準")
    spec2 = simplify_sku_name(spec2 or "") if spec2 else ""
    key = sku_spec_combo_key(spec1, spec2)
    if key and key not in used:
        used.add(key)
        return spec1, spec2

    fallback = simplify_sku_name(raw_spec or "")
    if fallback and fallback != "標準":
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
    history = [item for item in list_history() if item.get("task_id") != task.get("task_id")]
    history.insert(0, task)
    history = history[:50]
    _write_json(HISTORY_FILE, history)
    _write_json(LATEST_RESULT_FILE, task)






