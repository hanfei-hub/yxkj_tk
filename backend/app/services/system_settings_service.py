from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import SystemSetting


DEFAULT_SYSTEM_SETTINGS = {
    "1688_match_threshold": ("1688 图片匹配分数", "90", "达到此分数才写回货源", "float", 0, 100),
    "1688_page_size": ("1688 每页候选数", "20", "每次从 1688 获取的商品数量", "int", 1, 100),
    "1688_max_candidates": ("1688 最大候选数", "200", "单个衍生品最多比对的候选商品数", "int", 1, 500),
    "1688_batch_limit": ("1688 单次处理量", "20", "一次后台任务处理的衍生品数量", "int", 1, 100),
    "derivatives_per_product": ("每个原商品衍生数量", "10", "每个 FastMoss 原商品生成的衍生品数量", "int", 1, 30),
    "fastmoss_page_size": ("FastMoss 每次采集数", "20", "每次同步 FastMoss 的商品数量", "int", 1, 100),
}


def ensure_system_settings(db: Session) -> None:
    for key, values in DEFAULT_SYSTEM_SETTINGS.items():
        item = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
        if item:
            continue
        name, value, description, value_type, min_value, max_value = values
        db.add(
            SystemSetting(
                setting_key=key,
                setting_value=value,
                setting_name=name,
                description=description,
                value_type=value_type,
                min_value=min_value,
                max_value=max_value,
            )
        )


def get_setting_text(db: Session, key: str) -> str:
    item = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
    if item and item.setting_value != "":
        return item.setting_value
    return str(DEFAULT_SYSTEM_SETTINGS.get(key, ("", "", "", "", 0, 0))[1])


def get_setting_int(db: Session, key: str) -> int:
    try:
        value = int(float(get_setting_text(db, key)))
    except (TypeError, ValueError):
        value = int(float(DEFAULT_SYSTEM_SETTINGS.get(key, ("", "0", "", "", 0, 0))[1]))
    item = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
    if item:
        if item.min_value is not None:
            value = max(value, int(item.min_value))
        if item.max_value is not None:
            value = min(value, int(item.max_value))
    return value


def get_setting_float(db: Session, key: str) -> float:
    try:
        value = float(get_setting_text(db, key))
    except (TypeError, ValueError):
        value = float(DEFAULT_SYSTEM_SETTINGS.get(key, ("", "0", "", "", 0, 0))[1])
    item = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
    if item:
        if item.min_value is not None:
            value = max(value, float(item.min_value))
        if item.max_value is not None:
            value = min(value, float(item.max_value))
    return value
