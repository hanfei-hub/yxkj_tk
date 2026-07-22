from __future__ import annotations

import json
import os
import shutil
import uuid
import base64
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import BASE_DIR
from app.models.entities import ModelConfig, ThirdPartyConfig, VideoAsset, VideoProject, VideoStoryboardFrame, VideoTask
from app.services.ai_model_service import MODEL_TYPE_IMAGE_GENERATION, chat_completion, extract_json_object, get_model_config


VIDEO_RUNTIME_DIR = BASE_DIR / "runtime" / "video_generation"
VIDEO_ASSET_DIR = VIDEO_RUNTIME_DIR / "assets"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0-mini-260615"
SEEDANCE_MODEL_ALIASES = {
    "Doubao-Seedance-2.0-mini": "doubao-seedance-2-0-mini-260615",
    "Doubao-Seedance-2.0-Fast": "doubao-seedance-2-0-fast",
    "seedance-2.0-mini": "doubao-seedance-2-0-mini-260615",
    "seedance-2.0-fast": "doubao-seedance-2-0-fast",
}
DEFAULT_IMAGE_MODEL = "ep-20260710161912-qq7gf"
SEEDANCE_MINI_CNY_PER_1000_TOKENS = float(os.getenv("SEEDANCE_MINI_CNY_PER_1000_TOKENS", "0.023"))

SEEDANCE_PROMPT_GUIDE = """
Seedance prompt rules:
- Keep the video vertical 9:16 and about 15 seconds.
- Describe one clear subject, one main action, one environment, light, mood, and camera movement per shot.
- Avoid overloaded shots, conflicting actions, vague wording, and excessive lens changes.
- For ecommerce videos, keep product appearance, color, structure, and key details stable.
- Do not reinterpret the product as a wearable device, fitness ring, hula hoop, dumbbell, stand, toy, or another category unless the product details explicitly say so.
- Do not add missing parts, remove visible parts, change colors, change the ring/opening shape, or move controls/cables/buttons to new positions.
- If a shot would deform the product, switch to a simple tabletop close-up, hand-near-product gesture, or slow pan instead.
- For complex products, especially ring-shaped, cable-attached, segmented, or screen-equipped products, avoid body wearing, waist wrapping, two-hand pulling, fast rotation, swinging, or large human interaction.
- Prefer low-risk product display shots: tabletop hero shot, display stand shot, close-up details, screen/button close-up, cable/accessory close-up, hand pointing beside the product, or one finger lightly touching a button.
- Keep people out of the frame when possible. If a hand appears, show only a partial hand/finger near the product; do not grip, wear, pull, bend, or pass body parts through the product.
- Use a strong opening hook, visible selling points, realistic use scenes, and a final order prompt.
- Script and storyboard explanations are Chinese. Voiceover/subtitles must be in the selected video language.
""".strip()

VIRAL_ECOMMERCE_SCRIPT_GUIDE = """
Viral ecommerce short-video structure:
- Use a short-video selling rhythm inspired by high-performing YouTube/TikTok product videos, but keep product safety and accuracy higher priority.
- Start with a pain-point hook in the first 0-1 second, then immediately show the product or the problem it solves.
- Prefer frequent short shots: 0-1s hook, 1-2s product reveal, then 2-3 second detail/benefit shots. Do not make one long vague scene.
- Subtitle and voiceover should support each other: subtitles are short conclusion lines; voiceover explains the reason, benefit, price, or call-to-action.
- Use concrete selling logic: pain point -> product detail -> proof/use scene -> convenience/price -> order prompt.
- For complex products, keep this rhythm through camera cuts and close-ups, not through risky hand/body interaction.
- Do not copy platform-specific wording, watermarks, creator names, or exact scripts from any reference video.
""".strip()


VIDEO_STRATEGY_RULES = {
    "auto_safe": """
Selected shooting strategy: auto_safe.
- First decide whether the product is complex. Complex means ring-shaped, segmented, cable-attached, screen-equipped, transparent, reflective, flexible, or easy to confuse with another category.
- If complex, use the static_display strategy.
- If simple and rigid, allow light_interaction only.
- If wearable, allow wearable_demo only when the product details explicitly say it is clothing, jewelry, hat, shoes, glasses, bag, or another wearable item.
""".strip(),
    "static_display": """
Selected shooting strategy: static_display.
- Use this for complex structure products, ring-shaped products, products with screens/cables/buttons, or products that deform easily in video.
- Keep the product on a tabletop, product stand, shelf, or clean display stage for the whole video.
- No waist/body wearing, no hand gripping, no two-hand pulling, no swinging, no fast rotation, no body passing through the product.
- Shots should be: full hero product, slow push-in, screen/control close-up, structure/material close-up, cable/button/detail close-up, final beauty shot.
- If a human appears, show only a fingertip pointing near the product or lightly touching a button. The product remains still.
""".strip(),
    "light_interaction": """
Selected shooting strategy: light_interaction.
- The product stays on a table or stand. Allow only one safe interaction: one finger points to a detail, one finger taps a button, or a hand places the product down once.
- Do not show wearing, wrapping, pulling, bending, rotating, squeezing, or body contact.
- Keep all motion small and slow so the product geometry stays stable.
""".strip(),
    "handheld_demo": """
Selected shooting strategy: handheld_demo.
- Use only for simple, compact, rigid products that can be held naturally with one hand.
- If the product is ring-shaped, cable-attached, screen-equipped, segmented, flexible, or large, fall back to static_display.
- Use one-hand hold, slow tilt, and close-up detail shots. Avoid two-hand pulling, bending, fast motion, or body wearing.
""".strip(),
    "wearable_demo": """
Selected shooting strategy: wearable_demo.
- Use only for true wearable products such as clothes, jewelry, hats, shoes, glasses, bags, watches, or accessories meant to be worn.
- If the product is not explicitly wearable, fall back to static_display.
- Keep fitting scenes simple: slow reveal, no body/product interpenetration, no impossible bending, no shape changes.
""".strip(),
}


def video_strategy_key(project: VideoProject) -> str:
    details = project.product_details or ""
    for key in VIDEO_STRATEGY_RULES:
        if f"video_strategy_key:{key}" in details.replace(" ", ""):
            return key
    if "拍摄方案：静态展示" in details or "拍摄方案:静态展示" in details:
        return "static_display"
    if "拍摄方案：轻交互" in details or "拍摄方案:轻交互" in details:
        return "light_interaction"
    if "拍摄方案：手持演示" in details or "拍摄方案:手持演示" in details:
        return "handheld_demo"
    if "拍摄方案：佩戴演示" in details or "拍摄方案:佩戴演示" in details:
        return "wearable_demo"
    complex_terms = ["圆环", "环形", "呼啦", "带线", "线缆", "屏幕", "显示屏", "分段", "复杂结构", "ring", "cable", "screen"]
    wearable_terms = ["服装", "衣服", "裤", "裙", "鞋", "帽", "项链", "戒指", "手表", "眼镜", "包", "wearable"]
    lowered = details.lower()
    if any(term in lowered for term in complex_terms):
        return "static_display"
    if any(term in lowered for term in wearable_terms):
        return "wearable_demo"
    return "auto_safe"


def video_strategy_prompt(project: VideoProject) -> str:
    key = video_strategy_key(project)
    return VIDEO_STRATEGY_RULES.get(key, VIDEO_STRATEGY_RULES["auto_safe"])


def ensure_runtime_dirs() -> None:
    VIDEO_ASSET_DIR.mkdir(parents=True, exist_ok=True)


def public_asset_url(file_name: str) -> str:
    return f"/static/video_generation/assets/{file_name}"


def safe_json_loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except ValueError:
        return default


def first_int_value(data: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float, str)) and str(value).strip() != "":
            try:
                return int(float(value))
            except ValueError:
                continue
    return 0


def find_usage_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    for key in ("usage", "token_usage", "tokens", "billing", "bill_info"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    for value in data.values():
        if isinstance(value, dict):
            found = find_usage_payload(value)
            if found:
                return found
        elif isinstance(value, list):
            for item in value:
                found = find_usage_payload(item)
                if found:
                    return found
    return {}


def extract_token_usage(data: dict[str, Any], model_name: str) -> dict[str, Any]:
    usage = find_usage_payload(data)
    prompt_tokens = first_int_value(usage, ("prompt_tokens", "input_tokens", "input_token_count"))
    completion_tokens = first_int_value(usage, ("completion_tokens", "output_tokens", "output_token_count"))
    total_tokens = first_int_value(usage, ("total_tokens", "token_count", "tokens", "total_token_count", "billed_tokens"))
    if total_tokens <= 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens
    cost_cny = 0.0
    note = ""
    if total_tokens > 0 and "mini" in (model_name or "").lower():
        cost_cny = round(total_tokens * SEEDANCE_MINI_CNY_PER_1000_TOKENS / 1000, 6)
        note = f"按 Seedance 2.0 mini {SEEDANCE_MINI_CNY_PER_1000_TOKENS} 元/千 token 计算。"
    elif total_tokens > 0:
        note = "API 返回了 token，但当前模型未配置单价，费用请以火山账单为准。"
    else:
        note = "API 未返回 token，无法计算本次费用。"
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_cny": cost_cny,
        "note": note,
        "raw": usage,
    }


def first_text_value(data: Any, keys: tuple[str, ...]) -> str:
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value)
        for value in data.values():
            found = first_text_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = first_text_value(item, keys)
            if found:
                return found
    return ""


def apply_video_response(task: VideoTask, project: VideoProject, data: dict[str, Any]) -> None:
    task.response_payload = json.dumps(data, ensure_ascii=False)
    task.response_snapshot = json.dumps(data, ensure_ascii=False)
    usage = extract_token_usage(data, task.model_name)
    task.usage_prompt_tokens = int(usage["prompt_tokens"])
    task.usage_completion_tokens = int(usage["completion_tokens"])
    task.usage_total_tokens = int(usage["total_tokens"])
    task.usage_cost_cny = float(usage["cost_cny"])
    task.usage_note = str(usage["note"])
    task.usage_raw = json.dumps(usage["raw"], ensure_ascii=False)
    task.provider_task_id = task.provider_task_id or first_text_value(data, ("id", "task_id"))
    video_url = first_text_value(data, ("video_url", "result_video_url", "url", "output_url"))
    if video_url:
        task.video_url = video_url
        task.result_video_url = video_url
        project.result_video_url = video_url
    status = first_text_value(data, ("status", "state"))
    if video_url:
        task.status = "succeeded"
        project.status = "video_ready"
    elif status:
        task.status = status
        project.status = "video_submitted"


def asset_to_dict(asset: VideoAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "asset_type": asset.asset_type,
        "role": asset.role,
        "description": asset.description,
        "file_name": asset.file_name,
        "public_url": asset.public_url or asset.url,
        "is_primary": asset.is_primary,
        "created_at": asset.created_at.strftime("%Y-%m-%d %H:%M:%S") if asset.created_at else None,
    }


def frame_to_dict(frame: VideoStoryboardFrame) -> dict[str, Any]:
    return {
        "id": frame.id,
        "sort_order": frame.sort_order,
        "timeline": frame.timeline,
        "shot_type": frame.shot_type,
        "visual_cn": frame.visual_cn,
        "copy": frame.copy,
        "atmosphere_cn": frame.atmosphere_cn,
    }


def task_to_dict(task: VideoTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "generation_mode": task.generation_mode,
        "model_name": task.model_name,
        "provider_task_id": task.provider_task_id,
        "status": task.status,
        "video_url": task.video_url,
        "result_video_url": task.result_video_url,
        "local_video_path": task.local_video_path,
        "local_video_url": task.local_video_url,
        "usage_prompt_tokens": task.usage_prompt_tokens,
        "usage_completion_tokens": task.usage_completion_tokens,
        "usage_total_tokens": task.usage_total_tokens,
        "usage_cost_cny": task.usage_cost_cny,
        "usage_note": task.usage_note,
        "usage_raw": safe_json_loads(task.usage_raw, {}),
        "error_message": task.error_message,
        "response_payload": safe_json_loads(task.response_payload, {}),
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S") if task.created_at else None,
        "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M:%S") if task.updated_at else None,
    }


def project_to_dict(db: Session, project: VideoProject) -> dict[str, Any]:
    assets = db.scalars(select(VideoAsset).where(VideoAsset.project_id == project.id).order_by(VideoAsset.id)).all()
    frames = db.scalars(
        select(VideoStoryboardFrame).where(VideoStoryboardFrame.project_id == project.id).order_by(VideoStoryboardFrame.sort_order, VideoStoryboardFrame.id)
    ).all()
    tasks = db.scalars(select(VideoTask).where(VideoTask.project_id == project.id).order_by(VideoTask.id.desc())).all()
    return {
        "id": project.id,
        "user_id": project.user_id,
        "title": project.title,
        "target_market": project.target_market,
        "video_language": project.video_language,
        "product_details": project.product_details,
        "script_text": project.script_text,
        "script_json": safe_json_loads(project.script_json, {}),
        "status": project.status,
        "result_video_url": project.result_video_url,
        "assets": [asset_to_dict(asset) for asset in assets],
        "storyboard": [frame_to_dict(frame) for frame in frames],
        "tasks": [task_to_dict(task) for task in tasks],
        "created_at": project.created_at.strftime("%Y-%m-%d %H:%M:%S") if project.created_at else None,
        "updated_at": project.updated_at.strftime("%Y-%m-%d %H:%M:%S") if project.updated_at else None,
    }


def list_projects(db: Session, user: dict[str, Any]) -> list[dict[str, Any]]:
    query = select(VideoProject).order_by(VideoProject.updated_at.desc(), VideoProject.id.desc())
    if user.get("role") != "admin":
        query = query.where(VideoProject.user_id == int(user.get("id") or 0))
    return [project_to_dict(db, project) for project in db.scalars(query).all()]


def get_project(db: Session, project_id: int, user: dict[str, Any]) -> VideoProject:
    project = db.get(VideoProject, project_id)
    if not project:
        raise ValueError("Video project not found.")
    if user.get("role") != "admin" and project.user_id != int(user.get("id") or 0):
        raise PermissionError("No permission for this video project.")
    return project


def save_asset(db: Session, project: VideoProject, source_path: str, role: str, description: str, is_primary: bool) -> VideoAsset:
    ensure_runtime_dirs()
    ext = Path(source_path).suffix or ".png"
    file_name = f"{project.id}_{uuid.uuid4().hex}{ext}"
    dest = VIDEO_ASSET_DIR / file_name
    shutil.copyfile(source_path, dest)
    asset = VideoAsset(
        project_id=project.id,
        user_id=project.user_id,
        asset_type="product_image",
        role=role,
        description=description,
        file_name=file_name,
        file_path=str(dest),
        url=public_asset_url(file_name),
        sort_order=0,
        public_url=public_asset_url(file_name),
        is_primary=1 if is_primary else 0,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def normalize_frame(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "sort_order": int(raw.get("sort_order") or index),
        "timeline": str(raw.get("timeline") or raw.get("time") or ""),
        "shot_type": str(raw.get("shot_type") or raw.get("shot") or ""),
        "visual_cn": str(raw.get("visual_cn") or raw.get("visual") or raw.get("image") or ""),
        "copy": str(raw.get("copy") or raw.get("subtitle") or raw.get("voiceover") or ""),
        "atmosphere_cn": str(raw.get("atmosphere_cn") or raw.get("quality") or raw.get("mood") or ""),
    }


def script_text_from_frames(data: dict[str, Any]) -> str:
    title = data.get("title") or ""
    hook = data.get("hook") or ""
    selling_points = data.get("selling_points") or []
    frames = data.get("storyboard") or []
    lines = [f"标题：{title}", f"开头钩子：{hook}"]
    if selling_points:
        lines.append("卖点：" + "；".join(str(item) for item in selling_points))
    for frame in frames:
        item = normalize_frame(frame, len(lines))
        lines.append(
            f"{item['timeline']} | {item['shot_type']} | 画面：{item['visual_cn']} | 字幕/口播：{item['copy']} | 氛围与画质：{item['atmosphere_cn']}"
        )
    return "\n".join(lines)


def save_script_frames(db: Session, project: VideoProject, frames: list[dict[str, Any]]) -> None:
    db.execute(delete(VideoStoryboardFrame).where(VideoStoryboardFrame.project_id == project.id))
    for index, raw in enumerate(frames, start=1):
        item = normalize_frame(raw, index)
        db.add(
            VideoStoryboardFrame(
                project_id=project.id,
                user_id=project.user_id,
                frame_index=item["sort_order"],
                time_range=item["timeline"],
                shot_size=item["shot_type"],
                visual=item["visual_cn"],
                atmosphere_quality=item["atmosphere_cn"],
                prompt=item["visual_cn"],
                **item,
            )
        )


def generate_script(db: Session, project: VideoProject) -> dict[str, Any]:
    assets = db.scalars(select(VideoAsset).where(VideoAsset.project_id == project.id).order_by(VideoAsset.id)).all()
    image_notes = "\n".join(f"- {asset.role or 'product image'}: {asset.description}" for asset in assets)
    prompt = f"""
You are an ecommerce short-video script planner for Doubao Seedance.

Product information:
{project.product_details}

Target market: {project.target_market}
Voiceover/subtitle language: {project.video_language}
Uploaded image notes:
{image_notes or '- no image yet'}

{SEEDANCE_PROMPT_GUIDE}

{VIRAL_ECOMMERCE_SCRIPT_GUIDE}

{video_strategy_prompt(project)}

Shot planning constraints:
- Do not write scenes where a person wears the product, wraps it around waist/body/neck/arms, pulls it with both hands, swings it, or rotates it quickly.
- Keep the product stationary on a tabletop, display stand, sofa-side table, or clean product stage in most shots.
- Use only safe human interaction: one finger lightly touching a button, a hand pointing beside the product, or a hand placing the product on a table without gripping the ring.
- For ring-shaped products, never call it a hula hoop, fitness ring, belt, waist trainer, dumbbell, or exercise equipment unless product details explicitly say so.
- The 5 shots should follow this safer structure:
  1. Full product hero shot on a table or display stand.
  2. Slow push-in to the central screen/control area.
  3. Close-up of segmented structure, buttons, cable, and material.
  4. One finger lightly touches a button while the product stays still.
  5. Final clean product beauty shot with order call-to-action.

Return JSON only:
{{
  "title": "Chinese title",
  "hook": "Chinese hook",
  "selling_points": ["Chinese selling point"],
  "target_audience": "Chinese audience",
  "usage_scenes": ["Chinese scene"],
  "storyboard": [
    {{
      "sort_order": 1,
      "timeline": "0-3s",
      "shot_type": "Chinese shot size",
      "visual_cn": "Chinese visual description",
      "copy": "Japanese subtitle and voiceover line",
      "atmosphere_cn": "Chinese mood and quality"
    }}
  ]
}}
Use exactly 5 storyboard shots covering 0-15 seconds.
""".strip()
    answer = chat_completion(
        db,
        [{"role": "user", "content": prompt}],
        model_type="general",
        temperature=0.4,
        max_tokens=2800,
    )
    data = extract_json_object(answer)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object.")
    frames = data.get("storyboard") or []
    if not isinstance(frames, list):
        frames = []
    project.script_json = json.dumps(data, ensure_ascii=False)
    project.script_text = script_text_from_frames(data)
    project.status = "script_ready"
    save_script_frames(db, project, frames)
    db.commit()
    db.refresh(project)
    return project_to_dict(db, project)


def ark_config(db: Session) -> ThirdPartyConfig:
    service_types = ["volcengine_ark", "ark", "doubao_ark", "volcengine"]
    config = db.scalar(
        select(ThirdPartyConfig)
        .where(
            ThirdPartyConfig.status == 1,
            ThirdPartyConfig.service_type.in_(service_types),
            ThirdPartyConfig.access_key_encrypted != "",
        )
        .order_by(ThirdPartyConfig.id.desc())
    )
    if not config or not config.access_key_encrypted:
        raise ValueError("请先在第三方 API 配置启用火山方舟 Ark：volcengine_ark。")
    return config


def image_generation_config(db: Session) -> tuple[ThirdPartyConfig, str]:
    config = ark_config(db)
    model_config = db.scalar(
        select(ModelConfig)
        .where(ModelConfig.model_type == MODEL_TYPE_IMAGE_GENERATION, ModelConfig.status == 1)
        .order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
    )
    configured_endpoint = str(model_config.base_url or "").strip() if model_config else ""
    configured_model = str(model_config.model_name or "").strip() if model_config else ""
    model_name = (
        configured_endpoint
        if configured_endpoint.startswith("ep-")
        else configured_model
        or os.getenv("VIDEO_STORYBOARD_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    )
    return config, model_name


def absolute_public_url(path: str) -> str:
    value = (path or "").strip()
    if value.startswith(("http://", "https://", "data:")):
        return value
    public_base = os.getenv("TK_SELECTION_PUBLIC_BASE_URL", "http://120.26.207.89").rstrip("/")
    return f"{public_base}{value}" if value.startswith("/") else value


def request_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def product_assets(db: Session, project_id: int) -> list[VideoAsset]:
    return db.scalars(
        select(VideoAsset)
        .where(VideoAsset.project_id == project_id, VideoAsset.asset_type.in_(["product", "product_image", "storyboard_sheet"]))
        .order_by(VideoAsset.id)
    ).all()


def storyboard_prompt(project: VideoProject, assets: list[VideoAsset]) -> str:
    image_notes = "\n".join(
        f"- {asset.role or '产品图'}：{asset.description or '未填写'}，参考地址：{absolute_public_url(asset.public_url or asset.url)}"
        for asset in assets
        if asset.asset_type in {"product", "product_image"}
    )
    return f"""
请根据产品图、脚本和图片说明，生成一张 9:16 电商短视频分镜头拼图。

要求：
1. 拼图中展示 5 个连续分镜，按时间轴从上到下或从左到右清晰排列。
2. 每个分镜都要能看出画面主体、产品细节和场景动作。
3. 保持产品外观、颜色、结构、材质一致，不要改造产品。
4. 画面用于后续视频生成，不要做海报，不要加大段说明文字。
5. 可以在每个分镜角落保留很短的时间标记，但不要遮挡产品。
6. 画面质感真实、清晰、适合 TikTok 竖版带货短视频。

产品详情：
{project.product_details}

产品图说明：
{image_notes or "无"}

完整脚本：
{project.script_text}
""".strip()


def image_url_from_response(data: dict[str, Any]) -> tuple[str, str]:
    candidates: list[Any] = []
    if isinstance(data.get("data"), list):
        candidates.extend(data["data"])
    elif isinstance(data.get("data"), dict):
        candidates.append(data["data"])
    candidates.append(data)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("image_url")
        if url:
            return str(url), ""
        b64 = item.get("b64_json") or item.get("base64") or item.get("image_base64")
        if b64:
            return "", str(b64)
    return "", ""


def save_storyboard_sheet(db: Session, project: VideoProject, image_bytes: bytes) -> VideoAsset:
    ensure_runtime_dirs()
    file_name = f"{project.id}_storyboard_{uuid.uuid4().hex}.png"
    dest = VIDEO_ASSET_DIR / file_name
    dest.write_bytes(image_bytes)
    asset = VideoAsset(
        project_id=project.id,
        user_id=project.user_id,
        asset_type="storyboard_sheet",
        role="分镜头拼图",
        description="由脚本和产品细节图生成的分镜头画面拼图，用于图生视频。",
        file_name=file_name,
        file_path=str(dest),
        url=public_asset_url(file_name),
        sort_order=0,
        public_url=public_asset_url(file_name),
        is_primary=0,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def storyboard_prompt(project: VideoProject, assets: list[VideoAsset]) -> str:
    image_notes = "\n".join(
        f"- {asset.role or '产品图'}: {asset.description or '未填写'}; url={absolute_public_url(asset.public_url or asset.url)}"
        for asset in assets
        if asset.asset_type in {"product", "product_image"}
    )
    return f"""
请根据产品图、脚本和图片说明，生成一张 9:16 电商短视频分镜拼图。

商品外观锁定规则：
1. 上传的产品图是唯一正确商品，必须保持同一颜色、形状、结构、按钮、屏幕、线缆、连接件和分段细节。
2. 不要把商品改造成腰带、呼啦圈、哑铃、支架、玩具、挂件或其他品类，除非产品详情明确要求。
3. 不要新增底座球、哑铃杆、额外手柄、额外线缆、额外按钮；不要删掉参考图里已有的屏幕、线缆、按键和分段结构。
4. 不要改变商品本体比例，不要把圆环压扁、拉长、断开或做成软管。
5. 分镜只表现使用场景和镜头节奏；如果动作会导致商品变形，改用桌面展示、近景特写、手指指向或轻触商品。
6. 人手和商品要有合理遮挡关系，不能穿模，不能让手臂、身体、桌面或道具穿过商品。

分镜拼图要求：
1. 展示 5 个连续分镜，按时间轴排列。
2. 每个分镜都要能看出画面主体、商品细节和场景动作。
3. 画面用于后续视频生成，不要做海报，不要加大段说明文字。
4. 可在角落保留很短时间标记，但不要遮挡商品。
5. 画质真实、清晰、适合 TikTok 竖版带货短视频。

产品详情：
{project.product_details}

产品图说明：
{image_notes or "无"}

完整脚本：
{project.script_text}
""".strip()


def ensure_storyboard_sheet(db: Session, project: VideoProject, assets: list[VideoAsset]) -> VideoAsset:
    existing = next((asset for asset in reversed(assets) if asset.asset_type == "storyboard_sheet"), None)
    if existing and Path(existing.file_path or "").exists():
        return existing
    config, model_name = image_generation_config(db)
    endpoint = (config.api_base_url or DEFAULT_ARK_BASE_URL).rstrip("/")
    url = endpoint if endpoint.endswith("/images/generations") else f"{endpoint}/images/generations"
    reference_images: list[str] = []
    for asset in assets:
        if asset.asset_type in {"product", "product_image"}:
            reference_images.append(absolute_public_url(asset.public_url or asset.url))
    payload = {
        "model": model_name,
        "prompt": storyboard_prompt(project, assets),
        "image": reference_images,
        "response_format": "b64_json",
        "size": "1440x2560",
        "watermark": False,
        "sequential_image_generation": "disabled",
    }
    session = request_session()
    try:
        response = session.post(
            url,
            headers={"Authorization": f"Bearer {config.access_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        response_text = ""
        if getattr(exc, "response", None) is not None:
            response_text = (exc.response.text or "")[:1000]
        detail = f"：{response_text}" if response_text else ""
        raise ValueError(f"分镜头拼图生成失败：{exc}{detail}") from exc
    except ValueError as exc:
        raise ValueError("分镜头拼图接口返回的不是 JSON。") from exc
    image_url, b64 = image_url_from_response(data)
    if b64:
        image_bytes = base64.b64decode(b64)
    elif image_url:
        image_response = session.get(image_url, timeout=120)
        image_response.raise_for_status()
        image_bytes = image_response.content
    else:
        raise ValueError("分镜头拼图接口没有返回图片 URL 或 base64。")
    return save_storyboard_sheet(db, project, image_bytes)


def build_seedance_prompt(project: VideoProject, assets: list[VideoAsset], generation_mode: str) -> str:
    product_refs = []
    for index, asset in enumerate(assets, start=1):
        if asset.asset_type == "storyboard_sheet":
            continue
        line = f"Image {index}: role={asset.role or asset.asset_type}; description={asset.description}; url={absolute_public_url(asset.public_url or asset.url)}"
        product_refs.append(line)
    return f"""
Create a 9:16 ecommerce short video, 15 seconds, using image-to-video references only.

Product details:
{project.product_details}

Script:
{project.script_text}

Product reference images, highest priority:
{chr(10).join(product_refs) or '- missing product image'}

Storyboard and shot order:
Use the script text as the storyboard. Do not require a storyboard image reference.

{SEEDANCE_PROMPT_GUIDE}

{VIRAL_ECOMMERCE_SCRIPT_GUIDE}

{video_strategy_prompt(project)}

Hard product-consistency rules:
1. The product in the final video must match the uploaded product images exactly.
2. Keep the same product category, shape, structure, color, material, size impression, logo/label if visible, and key details.
3. Do not replace it with a similar product. Do not invent a different product. Do not simplify it into a generic object.
4. The script controls scene order and camera/action only. It must not override the real product images.
5. If a person uses or holds the product, the visible product must still match the reference images.
6. If the model cannot preserve the product exactly, use close-up shots of the reference product instead of generating a new object.
7. Avoid object interpenetration: hands, arms, body, table, packaging, and the product must not pass through each other.
8. Keep physical contact natural: when a hand holds the product, fingers wrap around the surface with correct depth and occlusion.
9. Avoid warped geometry, floating products, melted edges, broken straps, extra handles, duplicated parts, or impossible rotations.
10. Prefer stable close-ups and simple camera moves when showing product details, so the product shape stays consistent and readable.
11. Do not transform a ring-shaped product into a wearable belt, hula hoop, exercise equipment, dumbbell, lamp stand, toy, or decoration unless explicitly stated by the product details.
12. Do not create extra balls, bases, rods, handles, cables, buttons, screens, or decorative parts that are not visible in the product reference images.
13. Do not remove or relocate visible screens, buttons, cables, segmented panels, black bands, straps, or other reference-image details.
14. If any scene description conflicts with product reference images, ignore the conflicting scene detail and follow the product reference images.
15. Do not show the product being worn around the body, waist, neck, arms, or torso. Do not make the product touch or surround the body.
16. Do not show two hands pulling, stretching, bending, twisting, or gripping the ring. Use hands only for light pointing or one-finger button touch.
17. Keep the product mostly stationary on a table, display stand, shelf, sofa-side table, or clean product stage.
18. Use stable shots only: front hero shot, slow push-in, close-up pan, macro detail, screen close-up, button close-up, cable close-up, final product beauty shot.
19. If the script asks for wearing, waist use, active exercise, swinging, or fast motion, replace that action with a static tabletop demonstration and subtitle explanation.

Mode: image_to_video
The final video must include matching {project.video_language} subtitles and voiceover if the video model supports audio/subtitle generation. If unsupported, keep the subtitle text visually readable in the scene.
""".strip()


def normalize_seedance_model(model_name: str | None) -> str:
    value = (model_name or "").strip()
    return SEEDANCE_MODEL_ALIASES.get(value, value or DEFAULT_SEEDANCE_MODEL)


def create_video_task(db: Session, project: VideoProject, user_id: int, generation_mode: str, model_name: str | None = None) -> dict[str, Any]:
    config = ark_config(db)
    generation_mode = "image_to_video"
    assets = product_assets(db, project.id)
    product_reference_assets = [asset for asset in assets if asset.asset_type in {"product", "product_image"}]
    if not product_reference_assets:
        raise ValueError("图生视频至少需要上传 1 张产品图。")
    # Keep storyboard information in text only. Sending storyboard sheets can trip
    # Seedance privacy checks when the sheet contains generated people/faces.
    assets = product_assets(db, project.id)
    prompt = build_seedance_prompt(project, assets, generation_mode)
    model = normalize_seedance_model(model_name)
    endpoint = (config.api_base_url or DEFAULT_ARK_BASE_URL).rstrip("/")
    if endpoint.endswith("/contents/generations/tasks"):
        url = endpoint
    else:
        url = f"{endpoint}/contents/generations/tasks"

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    ordered_assets = sorted(
        [asset for asset in assets if asset.asset_type in {"product", "product_image"}],
        key=lambda item: (
            0 if item.is_primary else 1,
            item.id,
        ),
    )
    for asset in ordered_assets:
        image_item = {
            "type": "image_url",
            "image_url": {"url": absolute_public_url(asset.public_url or asset.url)},
            "role": "reference_image",
        }
        content.append(image_item)
    payload = {
        "model": model,
        "content": content,
        "duration": 15,
        "ratio": "9:16",
        "generate_audio": True,
        "watermark": False,
    }

    task = VideoTask(
        project_id=project.id,
        user_id=user_id,
        mode=generation_mode,
        provider="doubao",
        generation_mode=generation_mode,
        model_name=model,
        status="submitted",
        request_snapshot=json.dumps(payload, ensure_ascii=False),
        request_payload=json.dumps(payload, ensure_ascii=False),
    )
    db.add(task)
    db.flush()
    try:
        response = request_session().post(
            url,
            headers={"Authorization": f"Bearer {config.access_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        response_text = ""
        if getattr(exc, "response", None) is not None:
            response_text = (exc.response.text or "")[:1200]
        detail = f": {response_text}" if response_text else ""
        task.status = "failed"
        task.error_message = f"{exc}{detail}"
        project.status = "video_failed"
        db.commit()
        raise ValueError(f"Video API request failed: {exc}{detail}") from exc
    except ValueError as exc:
        task.status = "failed"
        task.error_message = "Video API returned non-JSON response."
        project.status = "video_failed"
        db.commit()
        raise ValueError("Video API returned non-JSON response.") from exc

    apply_video_response(task, project, data)
    if not task.provider_task_id:
        task.provider_task_id = str(data.get("id") or data.get("task_id") or data.get("data", {}).get("id") or "")
    if not task.status or task.status == "submitted":
        task.status = "submitted"
        project.status = "video_submitted"
    db.commit()
    db.refresh(task)
    return task_to_dict(task)


def refresh_video_task(db: Session, project: VideoProject, task_id: int) -> dict[str, Any]:
    task = db.get(VideoTask, task_id)
    if not task or task.project_id != project.id:
        raise ValueError("Video task not found.")
    if not task.provider_task_id:
        raise ValueError("Video task has no provider task id yet.")
    config = ark_config(db)
    endpoint = (config.api_base_url or DEFAULT_ARK_BASE_URL).rstrip("/")
    if endpoint.endswith("/contents/generations/tasks"):
        url = f"{endpoint}/{task.provider_task_id}"
    else:
        url = f"{endpoint}/contents/generations/tasks/{task.provider_task_id}"
    try:
        response = request_session().get(
            url,
            headers={"Authorization": f"Bearer {config.access_key_encrypted}", "Content-Type": "application/json"},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Video status query failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError("Video status API returned non-JSON response.") from exc
    apply_video_response(task, project, data)
    db.commit()
    db.refresh(task)
    return task_to_dict(task)
