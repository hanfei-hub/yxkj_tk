from __future__ import annotations

from datetime import datetime
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import ModelCallLog, TaskExecution


def utcnow() -> datetime:
    return datetime.utcnow()


def compact_json(value: Any, limit: int = 8000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text[:limit]


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


def create_task(
    db: Session,
    *,
    task_type: str,
    task_name: str = "",
    trigger_source: str = "api",
    total_count: int = 0,
    input_snapshot: Any = None,
) -> TaskExecution:
    task = TaskExecution(
        task_type=task_type,
        task_name=task_name or task_type,
        status="running",
        trigger_source=trigger_source,
        total_count=max(0, int(total_count or 0)),
        input_snapshot=compact_json(input_snapshot or {}),
        started_at=utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def finish_task(
    db: Session,
    task: TaskExecution | None,
    *,
    status: str = "success",
    processed_count: int = 0,
    success_count: int = 0,
    failed_count: int = 0,
    elapsed_ms_value: int = 0,
    result_snapshot: Any = None,
    error_message: str = "",
) -> None:
    if not task:
        return
    task.status = status
    task.processed_count = max(0, int(processed_count or 0))
    task.success_count = max(0, int(success_count or 0))
    task.failed_count = max(0, int(failed_count or 0))
    task.elapsed_ms = max(0, int(elapsed_ms_value or 0))
    task.result_snapshot = compact_json(result_snapshot or {})
    task.error_message = str(error_message or "")[:4000]
    task.finished_at = utcnow()
    db.commit()


def message_stats(messages: list[dict[str, Any]]) -> tuple[int, int, str]:
    chars = 0
    images = 0
    previews: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "image_url":
                    images += 1
                    continue
                text = str(part.get("text") or "")
                chars += len(text)
                if text:
                    previews.append(text[:300])
        else:
            text = str(content or "")
            chars += len(text)
            if text:
                previews.append(text[:300])
    return chars, images, "\n".join(previews)[:1000]


def log_model_call(
    db: Session,
    *,
    task_id: int | None,
    model_config_id: int | None,
    model_type: str,
    provider: str,
    model_name: str,
    status: str,
    elapsed_ms_value: int,
    prompt_chars: int,
    response_chars: int,
    image_count: int,
    temperature: float | None,
    max_tokens: int | None,
    error_message: str = "",
    request_preview: str = "",
    response_preview: str = "",
) -> None:
    item = ModelCallLog(
        task_id=task_id,
        model_config_id=model_config_id,
        model_type=model_type,
        provider=provider,
        model_name=model_name,
        status=status,
        elapsed_ms=max(0, int(elapsed_ms_value or 0)),
        prompt_chars=max(0, int(prompt_chars or 0)),
        response_chars=max(0, int(response_chars or 0)),
        image_count=max(0, int(image_count or 0)),
        temperature=temperature,
        max_tokens=max_tokens,
        error_message=str(error_message or "")[:4000],
        request_preview=str(request_preview or "")[:1000],
        response_preview=str(response_preview or "")[:1000],
    )
    db.add(item)
    db.commit()
