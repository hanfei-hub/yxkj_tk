from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base, engine
from app.core.security import hash_password
from app.models.entities import (
    DailyRecommendation,
    DerivedProductAttributeScore,
    DerivedProductRecommendation,
    FmProduct,
    ModelConfig,
    SelectionAttribute,
    ThirdPartyConfig,
    User,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        seed_all(db)
        ensure_volcengine_auto_publish_models(db)
    finally:
        db.close()


def seed_all(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        return

    users = [
        User(username="admin", password_hash=hash_password("admin123"), real_name="系统管理员", role="admin", status=1),
        User(username="teacher", password_hash=hash_password("teacher123"), real_name="选品老师", role="teacher", status=1),
        User(username="student", password_hash=hash_password("student123"), real_name="学生账号", role="student", status=1),
    ]
    db.add_all(users)

    db.add(
        ModelConfig(
            config_name="默认兼容模型",
            provider="custom",
            base_url="https://api.example.com/v1",
            model_name="configurable-chat-model",
            temperature=0.7,
            max_tokens=2000,
            is_default=1,
            status=1,
            remark="MVP 占位配置，后续在管理员页面替换为真实模型。",
        )
    )

    db.add_all(
        [
            ThirdPartyConfig(
                config_name="FastMoss 日本区 API",
                service_type="fastmoss",
                api_base_url="https://api.fastmoss.example",
                status=1,
                remark="已有 API 权限，待录入真实密钥。",
            ),
            ThirdPartyConfig(
                config_name="1688 寻源适配器",
                service_type="1688_api",
                status=0,
                remark="第三方形式待定，支持 API 或 MySQL。",
            ),
        ]
    )

    attributes = [
        SelectionAttribute(attribute_name="周期性", attribute_code="periodicity", attribute_type="scene", description="是否存在季节、节日、复购或周期消费关系。", default_weight=1.0, current_weight=1.0, is_system=1),
        SelectionAttribute(attribute_name="使用场景", attribute_code="usage_scene", attribute_type="scene", description="是否共享或延展原商品使用场景。", default_weight=1.2, current_weight=1.2, is_system=1),
        SelectionAttribute(attribute_name="同属新奇特", attribute_code="novelty", attribute_type="novelty", description="是否具备短视频可展示的新奇特属性。", default_weight=1.3, current_weight=1.3, is_system=1),
        SelectionAttribute(attribute_name="人群匹配", attribute_code="crowd_match", attribute_type="crowd", description="是否面向相似或可迁移用户群。", default_weight=1.4, current_weight=1.4, is_system=1),
        SelectionAttribute(attribute_name="价格带匹配", attribute_code="price_match", attribute_type="price", description="是否符合日本 TikTok 电商常见价格带。", default_weight=1.0, current_weight=1.0, is_system=1),
        SelectionAttribute(attribute_name="内容传播性", attribute_code="content_viral", attribute_type="novelty", description="是否适合短视频展示和种草。", default_weight=1.5, current_weight=1.5, is_system=1),
        SelectionAttribute(attribute_name="物流友好度", attribute_code="logistics", attribute_type="logistics", description="体积、重量、破损风险是否适合跨境。", default_weight=0.8, current_weight=0.8, is_system=1),
        SelectionAttribute(attribute_name="侵权风险", attribute_code="ip_risk", attribute_type="risk", description="是否存在品牌、外观、专利等风险。", default_weight=1.6, current_weight=1.6, is_system=1),
    ]
    db.add_all(attributes)

    products = [
        FmProduct(id=101, fm_product_id="fm_101", title="便携式猫咪自动饮水器", price=2980, sales_count=18420, rank_no=1, category="宠物用品", comment_count=862, data_date=str(date.today())),
        FmProduct(id=102, fm_product_id="fm_102", title="厨房水槽防溅伸缩挡板", price=1680, sales_count=12680, rank_no=2, category="家居厨房", comment_count=493, data_date=str(date.today())),
        FmProduct(id=103, fm_product_id="fm_103", title="桌面迷你加湿香薰灯", price=2280, sales_count=9780, rank_no=3, category="生活小家电", comment_count=331, data_date=str(date.today())),
    ]
    db.add_all(products)
    db.flush()

    derived = [
        DerivedProductRecommendation(id=1001, source_product_id=101, derived_title="猫咪循环过滤饮水机滤芯套装", derived_description="围绕自动饮水器形成复购型耗材，适合做低客单补充品。", recommendation_reason="原商品评论集中提到清洁、滤芯更换和水质问题，耗材复购逻辑明确。", target_audience="养猫家庭、重视宠物健康的年轻用户", usage_scene="宠物饮水维护、日常补充耗材", risk_notes="需确认滤芯规格兼容性，避免品牌侵权描述。", ai_score=88, weighted_score=90),
        DerivedProductRecommendation(id=1002, source_product_id=101, derived_title="宠物饮水区防滑吸水垫", derived_description="解决饮水器周边湿滑、打翻和清洁问题。", recommendation_reason="评论中多次出现地面湿、清理麻烦，场景痛点明确。", target_audience="养猫养狗家庭", usage_scene="宠物饮水区清洁和防滑", risk_notes="同质化较强，需要图案、尺寸或材质差异化。", ai_score=81, weighted_score=83, supplier_search_status="has_result"),
        DerivedProductRecommendation(id=1003, source_product_id=101, derived_title="猫咪透明太空舱背包", derived_description="宠物外出携带用品，视觉强但和原商品场景跨度较大。", recommendation_reason="同为宠物人群，短视频展示强，但不属于原饮水场景延展。", target_audience="爱晒宠、经常带宠物外出的用户", usage_scene="宠物外出", risk_notes="体积较大，物流成本和售后风险较高。", ai_score=69, weighted_score=64, review_status="approved"),
        DerivedProductRecommendation(id=2001, source_product_id=102, derived_title="厨房台面吸水速干垫", derived_description="水槽周边收纳与防潮清洁衍生品。", recommendation_reason="和防溅挡板处于同一厨房清洁场景，容易组合销售。", target_audience="小户型家庭、厨房收纳用户", usage_scene="厨房水槽清洁", risk_notes="需注意材质差异化。", ai_score=84, weighted_score=85, supplier_search_status="has_result"),
        DerivedProductRecommendation(id=3001, source_product_id=103, derived_title="桌面氛围夜灯香薰片", derived_description="围绕桌面香薰灯做低价耗材和氛围配件。", recommendation_reason="具备复购和场景搭配关系，适合用氛围感内容展示。", target_audience="学生、办公室人群、独居女性", usage_scene="桌面办公、睡前放松", risk_notes="香薰类需要关注成分合规和运输限制。", ai_score=86, weighted_score=87),
    ]
    db.add_all(derived)
    db.flush()

    score_rows = [
        (101, 1001, 1, 92, "滤芯具备固定更换周期。"),
        (101, 1001, 2, 95, "与原商品完全处于同一使用场景。"),
        (101, 1001, 4, 90, "同样面向养猫用户。"),
        (101, 1002, 2, 88, "围绕饮水器周边使用。"),
        (101, 1002, 4, 86, "目标人群高度重合。"),
        (101, 1002, 6, 72, "清洁对比内容可展示，但新奇程度一般。"),
        (101, 1003, 3, 78, "视觉展示较强。"),
        (101, 1003, 4, 80, "同样面向宠物用户。"),
        (101, 1003, 7, 45, "体积偏大。"),
        (102, 2001, 2, 92, "同一厨房水槽场景。"),
        (102, 2001, 5, 86, "低客单易成交。"),
        (102, 2001, 7, 90, "轻小件。"),
        (103, 3001, 1, 85, "香薰片有耗材复购。"),
        (103, 3001, 2, 90, "同一桌面氛围场景。"),
        (103, 3001, 6, 84, "氛围变化适合短视频展示。"),
    ]
    db.add_all(
        [
            DerivedProductAttributeScore(
                source_product_id=source_id,
                recommendation_id=recommendation_id,
                attribute_id=attribute_id,
                ai_score=score,
                ai_reason=reason,
            )
            for source_id, recommendation_id, attribute_id, score, reason in score_rows
        ]
    )

    daily_source = derived * 2
    db.add_all(
        [
            DailyRecommendation(
                recommendation_date=str(date.today()),
                source_product_id=item.source_product_id,
                recommendation_id=item.id,
                title=item.derived_title,
                price=980 + index * 180,
                sales_count=3000 + index * 420,
                reason_summary=item.recommendation_reason,
                sort_order=index + 1,
            )
            for index, item in enumerate(daily_source[:10])
        ]
    )
    db.commit()


def ensure_volcengine_auto_publish_models(db: Session) -> None:
    ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    existing = db.scalars(select(ModelConfig)).all()
    reusable_key = next(
        (
            item.api_key_encrypted
            for item in existing
            if item.api_key_encrypted and ("ark" in item.base_url.lower() or "volces.com" in item.base_url.lower())
        ),
        "",
    )
    has_default = any(item.status == 1 and item.is_default == 1 for item in existing)
    wanted = [
        {
            "config_name": "Auto Publish Text - doubao-seed-2-0-lite",
            "provider": "volcengine_ark",
            "base_url": ark_base_url,
            "model_name": "ep-20260710160935-grs59",
            "temperature": 0.2,
            "max_tokens": 1800,
            "is_default": 0 if has_default else 1,
            "status": 1,
            "remark": "auto_publish:listing_text,image_analysis primary; model=doubao-seed-2-0-lite",
        },
        {
            "config_name": "Auto Publish Text - doubao-seed-2-1-pro",
            "provider": "volcengine_ark",
            "base_url": ark_base_url,
            "model_name": "ep-20260626105633-4gdhv",
            "temperature": 0.2,
            "max_tokens": 2400,
            "is_default": 0,
            "status": 1,
            "remark": "auto_publish:listing_text fallback; model=doubao-seed-2-1-pro",
        },
        {
            "config_name": "Auto Publish Translation - Doubao-Seed-Translation",
            "provider": "volcengine_ark",
            "base_url": ark_base_url,
            "model_name": "ep-20260713102020-zgh99",
            "temperature": 0.1,
            "max_tokens": 1800,
            "is_default": 0,
            "status": 1,
            "remark": "auto_publish:image_text_translation; model=Doubao-Seed-Translation",
        },
        {
            "config_name": "Auto Publish Image - doubao-seedream-5-0",
            "provider": "volcengine_ark",
            "base_url": ark_base_url,
            "model_name": "ep-20260710161912-qq7gf",
            "temperature": 0.2,
            "max_tokens": 2000,
            "is_default": 0,
            "status": 1,
            "remark": "auto_publish:image_generation,image_edit low_cost; model=doubao-seedream-5-0",
        },
        {
            "config_name": "Auto Publish Image - doubao-seedream-5-0-pro",
            "provider": "volcengine_ark",
            "base_url": ark_base_url,
            "model_name": "ep-20260710162015-r5rv9",
            "temperature": 0.2,
            "max_tokens": 2000,
            "is_default": 0,
            "status": 1,
            "remark": "auto_publish:image_generation,image_edit high_quality; model=doubao-seedream-5-0-pro",
        },
    ]
    changed = False
    existing_by_name = {item.config_name: item for item in existing}
    existing_by_model = {item.model_name: item for item in existing}
    for row in wanted:
        item = existing_by_name.get(row["config_name"]) or existing_by_model.get(row["model_name"])
        if item:
            if not item.api_key_encrypted and reusable_key:
                item.api_key_encrypted = reusable_key
                changed = True
            if item.model_name != row["model_name"]:
                item.model_name = row["model_name"]
                changed = True
            if not item.base_url:
                item.base_url = row["base_url"]
                changed = True
            if not item.provider:
                item.provider = row["provider"]
                changed = True
            if "auto_publish:" not in (item.remark or ""):
                item.remark = (item.remark + " " if item.remark else "") + row["remark"]
                changed = True
            continue
        db.add(ModelConfig(api_key_encrypted=reusable_key, **row))
        changed = True
    active_endpoint_ids = {
        "ep-20260710160935-grs59",
        "ep-20260626105633-4gdhv",
        "ep-20260713102020-zgh99",
        "ep-20260710161912-qq7gf",
        "ep-20260710162015-r5rv9",
    }
    for item in existing:
        text = f"{item.config_name} {item.model_name} {item.remark}".lower()
        if "doubao-seed-1.8" in text or "doubao-seed-1-8" in text:
            item.status = 0
            changed = True
        if "auto_publish:" in text and item.model_name not in active_endpoint_ids:
            item.status = 0
            changed = True
    if changed:
        db.commit()
