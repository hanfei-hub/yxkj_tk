from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import SelectionRestrictionRule


DEFAULT_RESTRICTION_WEIGHTS: dict[str, float] = {
    "目标人群": 25.0,
    "使用场景": 25.0,
    "功能/动词": 25.0,
    "商品周期性": 25.0,
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").strip().lower()
    return [token for token in re.split(r"[\s,，、|/;；]+", text) if token]


def _contains_any(rule_value: Any, target: str) -> tuple[bool, int]:
    tokens = _tokens(rule_value)
    hits = [token for token in tokens if token in target]
    return bool(hits), len(hits)


def _normalize_weights(values: dict[str, Any]) -> dict[str, float]:
    raw = {name: max(0.0, float(values.get(name) or 0)) for name in DEFAULT_RESTRICTION_WEIGHTS}
    total = sum(raw.values())
    if total <= 0:
        return dict(DEFAULT_RESTRICTION_WEIGHTS)
    normalized: dict[str, float] = {}
    running = 0.0
    names = list(raw)
    for name in names[:-1]:
        value = round(raw[name] / total * 100, 2)
        normalized[name] = value
        running += value
    normalized[names[-1]] = round(100 - running, 2)
    return normalized


def restriction_weights_for_product(db: Session, *, title: str, category: str, region: str = "JP") -> tuple[dict[str, float], dict[str, Any]]:
    """Return the best keyword-rule weights for a product, or equal defaults."""
    title_text = str(title or "").strip().lower()
    category_text = str(category or "").strip().lower()
    region_text = str(region or "JP").strip().upper()
    rules = list(db.scalars(
        select(SelectionRestrictionRule)
        .where(SelectionRestrictionRule.status == 1)
        .where(SelectionRestrictionRule.region.in_([region_text, "", "ALL"]))
        .order_by(SelectionRestrictionRule.id.asc())
    ).all())
    ranked: list[tuple[int, int, SelectionRestrictionRule]] = []
    for rule in rules:
        category_hit, category_count = _contains_any(rule.category_keyword, category_text)
        title_hit, title_count = _contains_any(rule.title_keyword, title_text)
        if not category_hit and not title_hit:
            continue
        # A rule matching both fields is more specific than one matching only one.
        score = (8 if category_hit and title_hit else 4 if title_hit else 2) + category_count + title_count
        specificity = len(_tokens(rule.category_keyword)) + len(_tokens(rule.title_keyword))
        ranked.append((score, specificity, rule))
    if not ranked:
        return dict(DEFAULT_RESTRICTION_WEIGHTS), {"matched": False, "rule_id": None, "rule_code": ""}
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2].id))
    rule = ranked[0][2]
    weights = _normalize_weights({
        "目标人群": rule.audience_weight,
        "使用场景": rule.scene_weight,
        "功能/动词": rule.verb_weight,
        "商品周期性": rule.periodicity_weight,
    })
    return weights, {"matched": True, "rule_id": rule.id, "rule_code": rule.rule_code or ""}


def restriction_weights_prompt(weights: dict[str, float], match_info: dict[str, Any]) -> str:
    source = "已匹配关键词规则" if match_info.get("matched") else "未匹配到关键词规则，使用默认均等权重"
    return (
        "\n商品族方向参考权重（来源：selection_restriction_rules）：\n"
        f"匹配状态：{source}\n"
        f"目标人群：{weights['目标人群']:.2f}%\n"
        f"使用场景：{weights['使用场景']:.2f}%\n"
        f"功能/动词：{weights['功能/动词']:.2f}%\n"
        f"商品周期性：{weights['商品周期性']:.2f}%\n"
        "请将以上权重作为衍生方向参考，权重越高的方向优先级越高；"
        "不要求每个维度都必须生成商品，不要按权重硬性分配商品数量，一个衍生品可以同时结合多个维度。\n"
    )
