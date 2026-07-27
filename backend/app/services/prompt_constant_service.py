from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AiPromptConstant


DEFAULT_PROMPT_CONSTANTS = {
    "jp_compliance_rules": (
        "日本区合规规则",
        "根据日本地区物流禁运、禁止进出口和平台禁售规则进行筛选。\n"
        "参考资料：\n"
        "https://support.oceanengine.com/support/content/144690?spaceId=235\n"
        "https://support.oceanengine.com/support/content/8457220354?mappingType=1&spaceId=235\n"
        "https://support.oceanengine.com/support/content/189021?mappingType=2&spaceId=235",
        "发送给大模型的日本市场合规约束。",
    ),
    "selection_constraints": (
        "选品分析固定规则",
        "只基于传入的商品名称、商品图片、价格、销量和当前选品维度分析；"
        "没有充足依据时必须标注‘无充足依据，仅作参考线索’；"
        "禁止虚构不存在的商品数据、销量、竞品和法规结论；"
        "衍生品名称必须适合后续 1688 关键词检索，输出内容使用简体中文。",
        "发送给大模型的通用选品约束。",
    ),
}


def ensure_prompt_constants(db: Session) -> None:
    for key, (name, content, remark) in DEFAULT_PROMPT_CONSTANTS.items():
        item = db.scalar(select(AiPromptConstant).where(AiPromptConstant.constant_key == key))
        if not item:
            db.add(
                AiPromptConstant(
                    constant_key=key,
                    constant_name=name,
                    constant_content=content,
                    status=1,
                    remark=remark,
                )
            )


def active_prompt_constants(db: Session) -> list[AiPromptConstant]:
    return list(
        db.scalars(
            select(AiPromptConstant)
            .where(AiPromptConstant.status == 1)
            .order_by(AiPromptConstant.id.asc())
        ).all()
    )


def prompt_constants_block(db: Session) -> str:
    items = active_prompt_constants(db)
    if not items:
        return ""
    sections = ["后台启用的大模型常量词表："]
    for item in items:
        sections.append(f"【{item.constant_name}】\n{item.constant_content.strip()}")
    return "\n\n".join(sections)
