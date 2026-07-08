from __future__ import annotations

import json
import re
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ModelConfig


class ModelCallError(RuntimeError):
    pass


def usable_model_filter():
    return (
        ModelConfig.status == 1,
        ModelConfig.api_key_encrypted != "",
        ModelConfig.base_url != "",
        ModelConfig.model_name != "",
    )


def get_default_model_config(db: Session) -> ModelConfig | None:
    doubao_config = db.scalar(
        select(ModelConfig)
        .where(*usable_model_filter(), ModelConfig.provider == "doubao")
        .order_by(ModelConfig.is_default.desc(), ModelConfig.id.desc())
    )
    if doubao_config:
        return doubao_config

    default_config = db.scalar(
        select(ModelConfig)
        .where(*usable_model_filter(), ModelConfig.is_default == 1)
        .order_by(ModelConfig.id.desc())
    )
    if default_config:
        return default_config

    return db.scalar(select(ModelConfig).where(*usable_model_filter()).order_by(ModelConfig.id.desc()))


def chat_completion(
    db: Session,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    config = get_default_model_config(db)
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
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {config.api_key_encrypted}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise ModelCallError(f"大模型请求失败：{exc}") from exc
    except ValueError as exc:
        raise ModelCallError("大模型返回内容不是 JSON。") from exc

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not answer:
        raise ModelCallError("大模型返回为空。")
    return str(answer).strip()


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
