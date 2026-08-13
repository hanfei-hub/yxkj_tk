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
    "smart_selection_intro": (
        "智能选品介绍",
        "智能选品系统会利用 AI 结合日本本地市场现状与消费潮流，挖掘出有机会走红的产品方向。\n"
        "确定产品方向之后，工具会在平台抓取大量同类商品数据，帮你摸清市面上同款的款式、定价、销量以及整体市场热度，完成大范围拓品。\n"
        "紧接着做多维度风险筛查，把禁运、禁售、侵权、受海关和平台规则限制的产品全部过滤掉。同时还会参考平台销量与竞争程度，避开内卷严重的成熟爆款，重点挖掘竞争更小的蓝海机会。\n"
        "完成筛选后自动产出完整选品报告，里面包含市场体量、用户需求走向、行业竞争情况、产品风险点以及可切入的机会参考。\n"
        "之后系统会自动对接 1688 供应链资源，为候选产品匹配合适的供货商，核算利润空间，评估报价、发货效率和供应链稳不稳定。\n"
        "最后综合流量表现、销量、合规情况、竞争压力、利润水平以及供应链实力，给出候选清单，输出经过层层把关的精选产品。",
        "导出报告中固定使用的智能选品介绍。",
    ),
    "derivation_pipeline_keywords": (
        "衍生品流水线关键词规则",
        "基于原商品生成同赛道、可替代、可升级和可组合的中文衍生商品名称，优先覆盖不同使用场景、价格带和细分人群；"
        "所有名称必须是简体中文，适合后续 1688 搜索，不得输出日文、英文或解释。",
        "衍生品任务第一步发送给 general 大模型的专用常量。",
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
