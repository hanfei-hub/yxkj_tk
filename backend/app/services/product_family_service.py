from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    DerivedProductDimensionReport,
    DerivedProductRecommendation,
    ProductFamily,
    ProductFamilyDimensionWeight,
    SelectionAttribute,
)


DIMENSIONS: list[tuple[str, str]] = [
    ("dimension_1", "使用场景"),
    ("dimension_2", "商品周期性"),
    ("dimension_3", "目标群体"),
    ("dimension_4", "短视频流量种草适配能力"),
    ("dimension_5", "日本市场偏好"),
    ("dimension_6", "是否属于新奇特商品"),
    ("dimension_7", "复购属性"),
    ("dimension_8", "竞品属性"),
]

INITIAL_WEIGHT = round(100 / len(DIMENSIONS), 4)


def active_dimensions(db: Session) -> list[tuple[str, str]]:
    """Return enabled dimension attributes from the database."""
    rows = db.scalars(
        select(SelectionAttribute)
        .where(SelectionAttribute.attribute_type == "dimension", SelectionAttribute.status == 1)
        .order_by(SelectionAttribute.id)
    ).all()
    dimensions: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        code = (row.attribute_code or "").strip()
        name = (row.attribute_name or "").strip()
        if code and name and code not in seen:
            dimensions.append((code, name))
            seen.add(code)
    return dimensions or list(DIMENSIONS)

STOPWORDS = {
    "日本",
    "跨境",
    "商品",
    "新品",
    "爆品",
    "一个",
    "一款",
    "套装",
    "组合",
    "专用",
    "适用",
    "儿童",
    "宝宝",
    "玩具",
    "男女",
    "学生",
    "家用",
    "便携",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def normalize_family_name(value: str) -> str:
    text = normalize_text(value)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def family_key_for_group(group: str) -> str:
    normalized = normalize_family_name(group) or "未命名商品族"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:24]


def parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        raw = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def tokenize_product_text(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text or ""):
        token = raw.strip().lower()
        if not token or token in STOPWORDS:
            continue
        tokens.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{5,}", token):
            for size in (2, 3, 4):
                for index in range(0, max(0, len(token) - size + 1)):
                    piece = token[index : index + size]
                    if piece not in STOPWORDS:
                        tokens.add(piece)
    return tokens


def family_tokens(family: ProductFamily) -> set[str]:
    text = " ".join(
        [
            family.family_group or "",
            family.family_variant or "",
            family.family_name or "",
            family.category_path or "",
            family.match_rule or "",
            " ".join(parse_json_list(family.normalized_keywords)),
        ]
    )
    return tokenize_product_text(text)


def score_existing_family(title: str, category: str, family: ProductFamily) -> float:
    product_tokens = tokenize_product_text(f"{title} {category}")
    existing_tokens = family_tokens(family)
    if not product_tokens or not existing_tokens:
        return 0.0
    overlap = product_tokens & existing_tokens
    if not overlap:
        return 0.0
    jaccard = len(overlap) / len(product_tokens | existing_tokens)
    coverage = len(overlap) / min(len(product_tokens), len(existing_tokens))
    name_bonus = 0.15 if normalize_family_name(family.family_group) in normalize_family_name(title) else 0.0
    return min(1.0, jaccard * 0.55 + coverage * 0.45 + name_bonus)


def best_local_family_match(db: Session, *, title: str, category: str, threshold: float = 0.42) -> ProductFamily | None:
    families = db.scalars(select(ProductFamily).order_by(ProductFamily.id.desc()).limit(300)).all()
    scored = [(score_existing_family(title, category, family), family) for family in families]
    scored = [item for item in scored if item[0] >= threshold]
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def normalize_family_info(raw: Any, *, title: str, category: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    keywords = raw.get("normalized_keywords") or raw.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(item).strip() for item in keywords if str(item).strip()]
    if not keywords:
        keywords = list(tokenize_product_text(f"{title} {category}"))[:8]

    group = str(raw.get("family_group") or raw.get("group") or "").strip()
    variant = str(raw.get("family_variant") or raw.get("variant") or "").strip()
    name = str(raw.get("family_name") or raw.get("name") or "").strip()
    if not group:
        group = fallback_family_group(title)
    if not variant:
        variant = fallback_family_variant(title, keywords)
    if not name:
        name = f"{group} / {variant}" if variant and variant != group else group

    match_rule = str(raw.get("match_rule") or raw.get("reason") or "").strip()
    if not match_rule:
        match_rule = f"动态分族；核心商品族={group}；变体={variant}；关键词={','.join(keywords[:8])}"

    return {
        "family_group": group[:128],
        "family_variant": variant[:128],
        "family_name": name[:255],
        "normalized_keywords": keywords[:16],
        "match_rule": match_rule[:2000],
        "category_path": str(category or "")[:255],
    }


def fallback_family_group(title: str) -> str:
    tokens = [token for token in tokenize_product_text(title) if token not in STOPWORDS]
    if not tokens:
        cleaned = re.sub(r"\s+", "", title or "")[:24]
        return cleaned or "未分类商品族"
    sorted_tokens = sorted(tokens, key=lambda item: (-len(item), item))
    return "".join(sorted_tokens[:2])[:32] or "未分类商品族"


def fallback_family_variant(title: str, keywords: list[str]) -> str:
    if keywords:
        return "".join(keywords[:2])[:32]
    return re.sub(r"\s+", "", title or "")[:32] or "通用变体"


def merge_family_keywords(family: ProductFamily, keywords: list[str]) -> None:
    merged = parse_json_list(family.normalized_keywords)
    for keyword in keywords:
        if keyword and keyword not in merged:
            merged.append(keyword)
    family.normalized_keywords = json.dumps(merged[:24], ensure_ascii=False)


def find_family_by_info(db: Session, info: dict[str, Any]) -> ProductFamily | None:
    family_key = family_key_for_group(info["family_group"])
    family = db.scalar(select(ProductFamily).where(ProductFamily.family_key == family_key))
    if family:
        return family
    normalized_group = normalize_family_name(info["family_group"])
    if not normalized_group:
        return None
    families = db.scalars(select(ProductFamily).order_by(ProductFamily.id.desc()).limit(500)).all()
    for item in families:
        if normalize_family_name(item.family_group) == normalized_group:
            return item
    return None


def create_family_by_info(db: Session, info: dict[str, Any]) -> ProductFamily:
    family = ProductFamily(
        family_key=family_key_for_group(info["family_group"]),
        family_group=info["family_group"],
        family_variant=info["family_variant"],
        family_name=info["family_name"],
        category_path=info.get("category_path") or "",
        normalized_keywords=json.dumps(info["normalized_keywords"], ensure_ascii=False),
        match_rule=info["match_rule"],
    )
    db.add(family)
    db.flush()
    return family


def get_or_create_product_family(
    db: Session,
    *,
    title: str,
    category: str = "",
    family_info: dict[str, Any] | None = None,
) -> ProductFamily:
    info = normalize_family_info(family_info or {}, title=title, category=category)

    # The database is the authority: model only proposes normalized family info.
    family = find_family_by_info(db, info)
    if not family and not family_info:
        family = best_local_family_match(db, title=title, category=category)

    if family:
        merge_family_keywords(family, info["normalized_keywords"])
        if info.get("category_path") and not family.category_path:
            family.category_path = info["category_path"]
        ensure_family_weights(db, family)
        return family

    family = create_family_by_info(db, info)
    ensure_family_weights(db, family)
    return family


def ensure_family_weights(db: Session, family: ProductFamily) -> None:
    existing = {
        item.dimension_code: item
        for item in db.scalars(
            select(ProductFamilyDimensionWeight).where(ProductFamilyDimensionWeight.family_id == family.id)
        ).all()
    }
    dimensions = active_dimensions(db)
    initial_weight = round(100 / len(dimensions), 4)
    for code, name in dimensions:
        if code not in existing:
            db.add(
                ProductFamilyDimensionWeight(
                    family_id=family.id,
                    dimension_code=code,
                    dimension_name=name,
                    weight_percent=initial_weight,
                )
            )
    db.flush()
    normalize_family_weights(db, family.id)


def weights_for_prompt(db: Session, family_id: int | None) -> dict[str, str]:
    dimensions = active_dimensions(db)
    initial_weight = round(100 / len(dimensions), 4)
    if not family_id:
        return {name: f"{initial_weight:.2f}%" for _, name in dimensions}
    family = db.get(ProductFamily, family_id)
    if family:
        ensure_family_weights(db, family)
    rows = db.scalars(
        select(ProductFamilyDimensionWeight)
        .where(ProductFamilyDimensionWeight.family_id == family_id)
        .order_by(ProductFamilyDimensionWeight.dimension_code)
    ).all()
    active_codes = {code for code, _ in dimensions}
    weights = {
        row.dimension_name: f"{float(row.weight_percent):.2f}%"
        for row in rows
        if row.dimension_code in active_codes
    }
    return weights or {name: f"{initial_weight:.2f}%" for _, name in dimensions}


def normalize_family_weights(db: Session, family_id: int) -> None:
    active_codes = {code for code, _ in active_dimensions(db)}
    rows = db.scalars(
        select(ProductFamilyDimensionWeight).where(
            ProductFamilyDimensionWeight.family_id == family_id,
            ProductFamilyDimensionWeight.dimension_code.in_(active_codes),
        )
    ).all()
    if not rows:
        return
    total = sum(max(0.1, float(row.weight_percent or 0)) for row in rows)
    if total <= 0:
        for row in rows:
            row.weight_percent = INITIAL_WEIGHT
        return
    running_total = 0.0
    for index, row in enumerate(rows):
        if index == len(rows) - 1:
            row.weight_percent = round(100 - running_total, 4)
        else:
            row.weight_percent = round(max(0.1, float(row.weight_percent or 0)) / total * 100, 4)
            running_total += float(row.weight_percent)


def attribute_to_dimension_code(attribute: SelectionAttribute | None) -> str | None:
    if not attribute:
        return None
    code = (attribute.attribute_code or "").strip()
    if attribute.attribute_type == "dimension" and code:
        return code
    name = (attribute.attribute_name or "").strip()
    for dimension_code, dimension_name in DIMENSIONS:
        if name == dimension_name:
            return dimension_code
    legacy_map = {
        "periodicity": "dimension_2",
        "usage_scene": "dimension_1",
        "crowd_match": "dimension_3",
        "content_viral": "dimension_4",
        "novelty": "dimension_6",
    }
    return legacy_map.get(code)


def adjust_family_weight_for_reject(
    db: Session,
    *,
    family_id: int | None,
    dimension_code: str | None,
    decrease_ratio: float = 0.9,
) -> None:
    if not family_id or not dimension_code:
        return
    row = db.scalar(
        select(ProductFamilyDimensionWeight).where(
            ProductFamilyDimensionWeight.family_id == family_id,
            ProductFamilyDimensionWeight.dimension_code == dimension_code,
        )
    )
    if not row:
        return
    row.reject_count += 1
    row.total_review_count += 1
    row.weight_percent = max(1.0, float(row.weight_percent or INITIAL_WEIGHT) * decrease_ratio)
    db.flush()
    normalize_family_weights(db, family_id)


def adjust_family_weights_for_approve(db: Session, *, family_id: int | None) -> None:
    if not family_id:
        return
    rows = db.scalars(
        select(ProductFamilyDimensionWeight).where(ProductFamilyDimensionWeight.family_id == family_id)
    ).all()
    for row in rows:
        row.approve_count += 1
        row.total_review_count += 1


def save_dimension_reports(
    db: Session,
    *,
    recommendation: DerivedProductRecommendation,
    analysis_report: Any,
) -> None:
    if not isinstance(analysis_report, dict):
        return
    dimensions = active_dimensions(db)
    weights = {
        row.dimension_code: float(row.weight_percent or INITIAL_WEIGHT)
        for row in db.scalars(
            select(ProductFamilyDimensionWeight).where(ProductFamilyDimensionWeight.family_id == recommendation.family_id)
        ).all()
    }
    for code, name in dimensions:
        value = analysis_report.get(code) or {}
        if not isinstance(value, dict):
            value = {}
        db.add(
            DerivedProductDimensionReport(
                recommendation_id=recommendation.id,
                family_id=recommendation.family_id,
                dimension_code=code,
                dimension_name=str(value.get("dimension_name") or name),
                rating_level=str(value.get("判定等级") or value.get("rating_level") or ""),
                analysis_content=str(value.get("客观分析内容") or value.get("analysis_content") or ""),
                weight_percent_snapshot=weights.get(code, INITIAL_WEIGHT),
            )
        )
