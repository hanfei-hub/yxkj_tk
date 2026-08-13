from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AiPromptConstant


DEFAULT_PROMPT_CONSTANTS = {
    "jp_compliance_rules": (
        "日本区商品合规风控规则（TikTok Shop 日本站）",
        "以下为日本站点禁售、限售、物流禁运及法令限制的审核要点，用于判断候选商品是否可在日本销售；"
        "命中任一项即判为不合规（compliant=false）并写明具体命中条款与原因。\n"
        "参考文档（官方规则，审核以文档为准）：\n"
        "【日本】禁售和暂不支持商品规则 https://support.oceanengine.com/support/content/144124?spaceId=235\n"
        "【日本】限售商品规则 https://support.oceanengine.com/support/content/144125?spaceId=235\n"
        "【日本】物流禁运/禁止进出口商品清单及他法令限制要求 https://support.oceanengine.com/support/content/144690?spaceId=235\n"
        "\n一、完全禁售（不允许销售）：\n"
        "1. 武器、弹药、爆炸物、管制刀具及仿真武器；\n"
        "2. 易燃、易爆、剧毒、腐蚀性、放射性等危险品；\n"
        "3. 毒品、麻醉及精神药物、制毒原料；\n"
        "4. 处方药及未经日本厚生劳动省（PMDA）批准的医药品；\n"
        "5. 野生动物及其制品（违反 CITES 华盛顿公约）；\n"
        "6. 活体动物、植物（检疫限制）；\n"
        "7. 人体器官、人体残骸；\n"
        "8. 烟草制品、电子烟及含尼古丁产品；\n"
        "9. 成人内容、色情商品；\n"
        "10. 赌博器材、彩票；\n"
        "11. 仿冒品、侵权/盗版商品（品牌、IP、动漫角色）；\n"
        "12. 货币、有价证券、伪造证件；\n"
        "13. 军警制服、徽章、警用器材；\n"
        "14. 黑客工具、窃听/偷拍设备；\n"
        "15. 政治敏感物品。\n"
        "\n二、暂不支持 / 需平台定邀（当前不可自行销售）：\n"
        "玩具与兴趣用品（部分）、手机配件（手机壳/膜/贴纸）、时尚首饰与配件（吊饰/吊坠/钥匙扣）、"
        "家居装饰/节庆/派对用品、笔记本及纸品、品牌/IP 随机盲盒（严禁商家自行装箱随机套盒）。\n"
        "\n三、限售（需报白/资质/审核后才能销售）：\n"
        "食品、饮料、食品补充剂：需标签、成分、产地、保质期、生产日期等合规文件；\n"
        "美妆及个护：需成分/标签/功能资料，禁止汞、对苯二酚等禁用成分及医用功效宣称；\n"
        "母婴用品：需认证书或测试报告，婴儿/产妇护肤及婴儿个护需报白；\n"
        "宠物食品/维生素/补充剂：需动物饲料企业通报、标签、成分、产地、期限；\n"
        "个护电器和医疗设备：需医疗器械销售许可/通报或检测资料；\n"
        "贵金属珠宝：需销售证书、检测报告及商品与包装图片；\n"
        "图书、出版物、音像；\n"
        "农药、肥料：需销售通报或申报资料；\n"
        "蓝牙/WiFi/无线电设备：需日本《电波法》技适认证（技适标记）；\n"
        "电器产品：需《电气用品安全法》（PSE）认证；\n"
        "玩具：需 ST 玩具安全标志等；\n"
        "酒精饮料：需酒类销售许可；\n"
        "二手/中古商品（部分品类禁售）。\n"
        "\n四、物流禁运 / 禁止进出口及其他法令限制：\n"
        "上述所有禁售品禁止进出口；\n"
        "含锂电池商品（移动电源、充电宝）：需 UN38.3，容量/功率受限，空运限制；\n"
        "粉末、液体、膏状、气雾剂（压缩气体）：运输受限；\n"
        "磁性材料；\n"
        "动植物检疫受限品（植物种子、木制品、肉类、乳制品）；\n"
        "受《药机法》《电气用品安全法》《食品卫法》《家电回收法》等限制的商品需对应合规文件。\n"
        "\n审核原则：宁可保守，命中即禁；对存疑商品标注具体命中条款与原因。",
        "发送给大模型的日本市场合规约束（依据 TikTok Shop 日本站三篇官方规则文档）。",
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
