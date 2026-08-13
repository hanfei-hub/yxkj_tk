from __future__ import annotations

import os

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import Base, engine
from app.core.security import hash_password
from app.models.entities import ModelConfig, RegionConfig, SelectionAttribute, SelectionRestrictionRule, SystemSetting, ThirdPartyConfig, User
from app.services.product_family_service import DIMENSIONS, INITIAL_WEIGHT
from app.services.selection_derivation_service import ensure_selection_prompt
from app.services.prompt_constant_service import ensure_prompt_constants
from app.services.system_settings_service import ensure_system_settings


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        ensure_dimension_attributes(db)
        ensure_system_settings(db)
        ensure_region_configs(db)
        seed_all(db)
        ensure_ark_third_party_config(db)
        ensure_echotik_third_party_config(db)
        ensure_selection_restriction_rules(db)
        ensure_selection_prompt(db)
        ensure_prompt_constants(db)
        db.commit()
    finally:
        db.close()


def ensure_region_configs(db: Session) -> None:
    marker_key = "region_config_seed_version"
    marker = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == marker_key))
    if marker and str(marker.setting_value).strip() == "2":
        return
    defaults = [
        ("中国", "CN"), ("美国", "US"), ("日本", "JP"), ("泰国", "TH"),
        ("越南", "VN"), ("马来西亚", "MY"), ("菲律宾", "PH"), ("新加坡", "SG"),
    ]
    db.query(RegionConfig).delete()
    for index, (name, code) in enumerate(defaults):
        db.add(RegionConfig(region_name=name, region_code=code, sort_order=index, status=1))
    if not marker:
        db.add(SystemSetting(
            setting_key=marker_key,
            setting_value="2",
            setting_name="国家和地区初始化版本",
            description="仅在版本升级时初始化默认国家和地区，后续管理员修改不会被覆盖。",
            value_type="system",
        ))
    else:
        marker.setting_value = "2"


def ensure_region_configs_legacy(db: Session) -> None:
    marker = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == "region_config_initialized"))
    if marker and str(marker.setting_value).strip() == "1":
        return
    defaults = [
        ("美国", "US"), ("印度尼西亚", "ID"), ("英国", "GB"), ("越南", "VN"),
        ("泰国", "TH"), ("马来西亚", "MY"), ("菲律宾", "PH"), ("西班牙", "ES"),
        ("墨西哥", "MX"), ("德国", "DE"), ("法国", "FR"), ("意大利", "IT"),
        ("巴西", "BR"), ("日本", "JP"), ("新加坡", "SG"),
    ]
    existing_count = int(db.scalar(select(func.count(RegionConfig.id))) or 0)
    if existing_count == 0:
        for index, (name, code) in enumerate(defaults):
            db.add(RegionConfig(region_name=name, region_code=code, sort_order=index))
    if not marker:
        marker = SystemSetting(
            setting_key="region_config_initialized",
            setting_value="1",
            setting_name="国家和地区初始化标记",
            description="仅用于首次初始化国家和地区，后续删除不会自动恢复。",
            value_type="system",
        )
        db.add(marker)
    else:
        marker.setting_value = "1"


def ensure_runtime_schema() -> None:
    derived_columns = {
        "owner_user_id": "INTEGER NULL",
        "family_id": "INTEGER NULL",
        "analysis_report": "TEXT",
        "source_search_keywords": "TEXT",
        "match_tags": "TEXT",
        "prompt_template_id": "INTEGER NULL",
        "model_used": "VARCHAR(128)",
        "supplier_product_id": "VARCHAR(128)",
        "supplier_title": "VARCHAR(512)",
        "supplier_image_url": "TEXT",
        "supplier_price": "FLOAT NULL",
        "supplier_currency": "VARCHAR(16) DEFAULT 'CNY'",
        "supplier_sales_count": "INTEGER",
        "supplier_shop_name": "VARCHAR(255)",
        "supplier_source_url": "TEXT",
        "supplier_match_score": "FLOAT",
        "supplier_match_report": "TEXT",
        "supplier_next_page": "INTEGER DEFAULT 1",
        "supplier_searched_count": "INTEGER DEFAULT 0",
        "supplier_raw_data": "TEXT",
    }
    fm_columns = {
        "family_id": "INTEGER NULL",
    }
    model_columns = {
        "model_type": "VARCHAR(64) DEFAULT 'general'",
    }
    third_party_columns = {
        "sign_name": "VARCHAR(128) DEFAULT ''",
        "template_code": "VARCHAR(128) DEFAULT ''",
    }
    user_columns = {
        "credit_balance": "INTEGER DEFAULT 0",
    }
    search_result_columns = {
        "source_type": "VARCHAR(32) DEFAULT 'ai_search'",
        "region": "VARCHAR(32) DEFAULT 'CN'",
        "currency": "VARCHAR(16) DEFAULT 'CNY'",
        "supplier_search_status": "VARCHAR(32) DEFAULT 'not_searched'",
        "supplier_next_page": "INTEGER DEFAULT 1",
        "supplier_searched_count": "INTEGER DEFAULT 0",
        "supplier_product_id": "VARCHAR(128) DEFAULT ''",
        "supplier_title": "VARCHAR(512) DEFAULT ''",
        "supplier_image_url": "TEXT",
        "supplier_price": "FLOAT NULL",
        "supplier_sales_count": "INTEGER DEFAULT 0",
        "supplier_shop_name": "VARCHAR(255) DEFAULT ''",
        "supplier_source_url": "TEXT",
        "supplier_match_score": "FLOAT NULL",
        "supplier_match_report": "TEXT",
    }
    video_project_columns = {
        "result_video_url": "TEXT",
    }
    video_asset_columns = {
        "public_url": "TEXT",
    }
    video_frame_columns = {
        "sort_order": "INTEGER DEFAULT 0",
        "timeline": "VARCHAR(64)",
        "shot_type": "VARCHAR(128)",
        "visual_cn": "TEXT",
        "atmosphere_cn": "TEXT",
    }
    video_task_columns = {
        "generation_mode": "VARCHAR(32) DEFAULT 'text_to_video'",
        "request_payload": "TEXT",
        "response_payload": "TEXT",
        "video_url": "TEXT",
        "usage_prompt_tokens": "INTEGER DEFAULT 0",
        "usage_completion_tokens": "INTEGER DEFAULT 0",
        "usage_total_tokens": "INTEGER DEFAULT 0",
        "usage_cost_cny": "FLOAT DEFAULT 0",
        "usage_note": "TEXT",
        "usage_raw": "TEXT",
    }
    selection_didadog_columns = {
        "selection_status": "VARCHAR(32) DEFAULT 'unreviewed'",
        "elimination_reason": "TEXT",
    }
    selection_pipeline_columns = {
        "pipeline_mode": "VARCHAR(32) DEFAULT 'selection'",
        "source_product_id": "INTEGER NULL",
    }
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect not in {"mysql", "sqlite"}:
            raise RuntimeError(f"Unsupported database dialect: {dialect}")
        ensure_columns(conn, dialect, "derived_product_recommendations", derived_columns)
        ensure_columns(conn, dialect, "fm_products", fm_columns)
        ensure_columns(conn, dialect, "model_configs", model_columns)
        ensure_columns(conn, dialect, "third_party_configs", third_party_columns)
        ensure_columns(conn, dialect, "users", user_columns)
        ensure_columns(conn, dialect, "user_search_recommendations", search_result_columns)
        ensure_columns(conn, dialect, "video_projects", video_project_columns)
        ensure_columns(conn, dialect, "video_assets", video_asset_columns)
        ensure_columns(conn, dialect, "video_storyboard_frames", video_frame_columns)
        ensure_columns(conn, dialect, "video_tasks", video_task_columns)
        ensure_columns(conn, dialect, "selection_didadog_products", selection_didadog_columns)
        ensure_columns(conn, dialect, "selection_pipeline_tasks", selection_pipeline_columns)


def ensure_columns(conn, dialect: str, table_name: str, columns: dict[str, str]) -> None:
    for column, definition in columns.items():
        if dialect == "mysql":
            exists = conn.execute(
                text(f"SHOW COLUMNS FROM {table_name} LIKE :column"),
                {"column": column},
            ).first()
        else:
            exists = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
            exists = any(row["name"] == column for row in exists)
        if not exists:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}"))


def ensure_dimension_attributes(db: Session) -> None:
    for code, name in DIMENSIONS:
        attribute = db.scalar(select(SelectionAttribute).where(SelectionAttribute.attribute_code == code))
        if not attribute:
            attribute = SelectionAttribute(
                attribute_name=name,
                attribute_code=code,
                attribute_type="dimension",
                description=f"衍生品审核维度：{name}",
                default_weight=INITIAL_WEIGHT,
                current_weight=INITIAL_WEIGHT,
                is_system=1,
                status=1,
            )
            db.add(attribute)
        else:
            attribute.attribute_name = name
            attribute.attribute_type = "dimension"
            attribute.description = f"衍生品审核维度：{name}"
            attribute.default_weight = INITIAL_WEIGHT
            attribute.current_weight = INITIAL_WEIGHT
            attribute.is_system = 1
            attribute.status = 1


def seed_all(db: Session) -> None:
    if not db.scalar(select(User).where(User.username == "admin")):
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin123"),
                real_name="系统管理员",
                role="admin",
                status=1,
            )
        )
    if not db.scalar(select(User).where(User.username == "teacher")):
        db.add(
            User(
                username="teacher",
                password_hash=hash_password("teacher123"),
                real_name="选品老师",
                role="teacher",
                status=1,
            )
        )
    if not db.scalar(select(User).where(User.username == "student")):
        db.add(
            User(
                username="student",
                password_hash=hash_password("student123"),
                real_name="学生账号",
                role="student",
                status=1,
            )
        )

    return

    if not db.scalar(select(ModelConfig).limit(1)):
        db.add(
            ModelConfig(
                config_name="默认兼容模型",
                provider="custom",
                model_type="general",
                base_url="https://api.example.com/v1",
                model_name="configurable-chat-model",
                temperature=0.7,
                max_tokens=2000,
                is_default=1,
                status=1,
                remark="占位配置，可在模型配置页面替换为真实模型。",
            )
        )


def ensure_ark_third_party_config(db: Session) -> None:
    existing = db.scalar(select(ThirdPartyConfig).where(ThirdPartyConfig.service_type == "volcengine_ark"))
    if not existing:
        db.add(
            ThirdPartyConfig(
                config_name="火山方舟 Ark",
                service_type="volcengine_ark",
                api_base_url="https://ark.cn-beijing.volces.com/api/v3",
                status=0,
                remark="统一填写火山方舟 API Key。Seedance 视频、生图分镜等 Ark 模型共用这一条配置。",
            )
        )

    if not db.scalar(select(ThirdPartyConfig).where(ThirdPartyConfig.service_type == "fastmoss")):
        db.add(
            ThirdPartyConfig(
                config_name="FastMoss 日本区 API",
                service_type="fastmoss",
                api_base_url="https://api.fastmoss.com",
                status=1,
                remark="FastMoss API 配置。",
            )
        )
    if not db.scalar(select(ThirdPartyConfig).where(ThirdPartyConfig.service_type == "1688_api")):
        db.add(
            ThirdPartyConfig(
                config_name="1688 寻源适配器",
                service_type="1688_api",
                status=0,
                remark="第三方 1688 API 接入占位。",
            )
        )
    if not db.scalar(select(ThirdPartyConfig).where(ThirdPartyConfig.service_type == "miaoshou_api")):
        db.add(
            ThirdPartyConfig(
                config_name="妙手开放平台 API",
                service_type="miaoshou_api",
                api_base_url="https://openapi-erp.91miaoshou.com",
                status=0,
                remark="请填写 AppKey 和 AppSecret；用于妙手开放平台签名调用。",
            )
        )


def ensure_echotik_third_party_config(db: Session) -> None:
    config = db.scalar(select(ThirdPartyConfig).where(ThirdPartyConfig.service_type == "echotik_api"))
    if not config:
        config = ThirdPartyConfig(
            config_name="EchoTik（滴答狗）",
            service_type="echotik_api",
            api_base_url="https://open.echotik.live",
            status=1,
            remark=(
                '{"photo_search_path":"/api/v3/realtime/product/photo-search",'
                '"photo_method":"POST","photo_image_field":"image_base64",'
                '"detail_path":"/api/v3/echotik/product/detail","detail_method":"GET",'
                '"detail_ids_field":"product_ids","detail_batch_size":10}'
            ),
        )
        db.add(config)
    username = os.getenv("ECHOTIK_USERNAME", "").strip()
    password = os.getenv("ECHOTIK_PASSWORD", "").strip()
    if username:
        config.access_key_encrypted = username
    if password:
        config.secret_key_encrypted = password


def ensure_selection_restriction_rules(db: Session) -> None:
    if db.scalar(select(SelectionRestrictionRule.id).limit(1)):
        return
    rules = [
        ("food_beverage_supplement", "食品、饮料和食品补充剂", "食品", "需要安全与合规文件、标签、成分、保质期和生产日期后报白。"),
        ("beauty_personal_care", "美妆及个护", "美妆 个护 化妆品 护肤", "需要标签、成分、功能、产地、期限等资料；医用声明、汞/对苯二酚等禁用成分禁止销售。"),
        ("mother_baby", "母婴用品", "母婴 婴儿 产妇 驱虫剂", "需要认证书或测试报告，婴儿护肤、产妇护肤和婴儿个护需报白。"),
        ("garden", "园艺用品", "园艺 杀虫剂 除草 肥料 土壤", "需要杀虫剂销售通报或肥料销售业务申报资料。"),
        ("personal_care_appliance_medical", "个护电器和医疗设备", "脱毛仪 正畸 月经杯 医疗器械", "需要医疗器械销售许可/通报或检测资料。"),
        ("pet", "宠物用品", "宠物食品 宠物维生素 宠物补充剂", "宠物食品、维生素和补充剂需要标签、成分、产地、期限和动物饲料企业通报。"),
        ("precious_metal_jewelry", "包含贵金属的珠宝", "贵金属 黄金 白金 铂金 珠宝", "需要销售证书、检测报告以及商品和包装图片。"),
        ("toy_hobby_unsupported", "玩具与兴趣用品（暂不支持）", "玩具 毛绒 娃娃 动作人偶 盲盒", "暂不支持或需平台定邀；品牌/IP/动漫角色商品存在高侵权风险。"),
        ("phone_accessory_unsupported", "手机配件（暂不支持）", "手机壳 屏幕保护膜 贴纸", "暂不支持或需平台定邀，注意品牌和 IP 侵权风险。"),
        ("fashion_accessory_unsupported", "时尚首饰与配件（暂不支持）", "吊饰 吊坠 钥匙扣", "暂不支持或需平台定邀，注意品牌和 IP 侵权风险。"),
        ("home_party_unsupported", "家居装饰、节庆及派对用品（暂不支持）", "派对袋 礼品 装饰贴纸", "暂不支持或需平台定邀，注意品牌和 IP 侵权风险。"),
        ("notebook_paper_unsupported", "笔记本及纸品（暂不支持）", "笔记本 纸品 文具", "仅限受邀商家销售，需要线上销售历史证明和平台定邀。"),
        ("blind_box", "盲盒类商品", "盲盒 神秘礼盒 金蛋 惊喜集换式卡牌", "严禁销售品牌、商家或达人自行装箱的随机套盒。"),
    ]
    for code, category_keyword, title_keyword, reason in rules:
        db.add(SelectionRestrictionRule(
            rule_code=code,
            region="JP",
            category_keyword=category_keyword,
            title_keyword=title_keyword,
            action="restricted",
            reason=reason,
            status=1,
        ))
