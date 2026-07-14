from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ModelConfig
from app.services.execution_log_service import log_model_call, message_stats


class ModelCallError(RuntimeError):
    pass


MODEL_TYPE_GENERAL = "general"
MODEL_TYPE_TEXT_TRANSLATION = "text_translation"
MODEL_TYPE_PRODUCT_VISION = "product_vision"
MODEL_TYPE_IMAGE_TRANSLATION = "image_translation"
MODEL_TYPE_IMAGE_GENERATION = "image_generation"


def usable_model_filter():
    return (
        ModelConfig.status == 1,
        ModelConfig.api_key_encrypted != "",
        ModelConfig.base_url != "",
        ModelConfig.model_name != "",
    )


def get_model_config(db: Session, model_type: str | None = None) -> ModelConfig | None:
    model_type = (model_type or "").strip()
    if model_type:
        typed_config = db.scalar(
            select(ModelConfig)
            .where(*usable_model_filter(), ModelConfig.model_type == model_type)
            .order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
        )
        if typed_config:
            return typed_config

    general_config = db.scalar(
        select(ModelConfig)
        .where(*usable_model_filter(), ModelConfig.model_type == MODEL_TYPE_GENERAL, ModelConfig.is_default == 1)
        .order_by(ModelConfig.id.desc())
    )
    if general_config:
        return general_config

    default_config = db.scalar(
        select(ModelConfig)
        .where(*usable_model_filter(), ModelConfig.is_default == 1)
        .order_by(ModelConfig.id.desc())
    )
    if default_config:
        return default_config

    doubao_config = db.scalar(
        select(ModelConfig)
        .where(*usable_model_filter(), ModelConfig.provider == "doubao")
        .order_by(ModelConfig.id.desc())
    )
    if doubao_config:
        return doubao_config

    return db.scalar(select(ModelConfig).where(*usable_model_filter()).order_by(ModelConfig.id.desc()))


def get_default_model_config(db: Session) -> ModelConfig | None:
    return get_model_config(db)


def chat_completion(
    db: Session,
    messages: list[dict[str, Any]],
    *,
    model_type: str | None = None,
    task_id: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    config = get_model_config(db, model_type=model_type)
    if not config:
        raise ModelCallError("未配置可用的大模型。")

    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    payload = {
        "model": config.model_name,
        "messages": messages,
        "temperature": temperature if temperature is not None else config.temperature,
        "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
    }
    if (config.provider or "").lower() == "doubao":
        payload["thinking"] = {"type": "disabled"}

    prompt_chars, image_count, request_preview = message_stats(messages)
    started = time.perf_counter()

    def write_log(status: str, response_text: str = "", error_message: str = "") -> None:
        log_model_call(
            db,
            task_id=task_id,
            model_config_id=config.id,
            model_type=config.model_type or model_type or "",
            provider=config.provider,
            model_name=config.model_name,
            status=status,
            elapsed_ms_value=int(round((time.perf_counter() - started) * 1000)),
            prompt_chars=prompt_chars,
            response_chars=len(response_text or ""),
            image_count=image_count,
            temperature=payload["temperature"],
            max_tokens=payload["max_tokens"],
            error_message=error_message,
            request_preview=request_preview,
            response_preview=(response_text or "")[:1000],
        )

    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=420,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        write_log("failed", error_message=str(exc))
        raise ModelCallError(f"大模型请求失败：{exc}") from exc
    except ValueError as exc:
        write_log("failed", error_message="model response is not json")
        raise ModelCallError("大模型返回内容不是 JSON。") from exc

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(answer, list):
        answer = "".join(str(part.get("text") or "") if isinstance(part, dict) else str(part) for part in answer)
    if not answer:
        write_log("failed", error_message="empty model response")
        raise ModelCallError("大模型返回为空。")
    answer_text = str(answer).strip()
    write_log("success", response_text=answer_text)
    return answer_text


def extract_json_object(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if not match:
        raise ModelCallError("大模型未返回可解析的 JSON。")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ModelCallError("大模型 JSON 解析失败。") from exc
