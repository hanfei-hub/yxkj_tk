from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import Base, engine
from app.core.security import hash_password
from app.models.entities import ModelConfig, SelectionAttribute, ThirdPartyConfig, User
from app.services.product_family_service import DIMENSIONS, INITIAL_WEIGHT
from app.services.selection_derivation_service import ensure_selection_prompt
from app.services.system_settings_service import ensure_system_settings


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        ensure_dimension_attributes(db)
        ensure_system_settings(db)
        seed_all(db)
        ensure_selection_prompt(db)
        db.commit()
    finally:
        db.close()


def ensure_runtime_schema() -> None:
    derived_columns = {
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
    user_columns = {
        "credit_balance": "INTEGER DEFAULT 0",
    }
    search_result_columns = {
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
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            for column, definition in derived_columns.items():
                exists = conn.execute(
                    text("SHOW COLUMNS FROM derived_product_recommendations LIKE :column"),
                    {"column": column},
                ).first()
                if not exists:
                    conn.execute(text(f"ALTER TABLE derived_product_recommendations ADD COLUMN {column} {definition}"))
            for column, definition in fm_columns.items():
                exists = conn.execute(
                    text("SHOW COLUMNS FROM fm_products LIKE :column"),
                    {"column": column},
                ).first()
                if not exists:
                    conn.execute(text(f"ALTER TABLE fm_products ADD COLUMN {column} {definition}"))
            for column, definition in model_columns.items():
                exists = conn.execute(
                    text("SHOW COLUMNS FROM model_configs LIKE :column"),
                    {"column": column},
                ).first()
                if not exists:
                    conn.execute(text(f"ALTER TABLE model_configs ADD COLUMN {column} {definition}"))
            for column, definition in user_columns.items():
                exists = conn.execute(
                    text("SHOW COLUMNS FROM users LIKE :column"),
                    {"column": column},
                ).first()
                if not exists:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {definition}"))
            for column, definition in search_result_columns.items():
                exists = conn.execute(
                    text("SHOW COLUMNS FROM user_search_recommendations LIKE :column"),
                    {"column": column},
                ).first()
                if not exists:
                    conn.execute(text(f"ALTER TABLE user_search_recommendations ADD COLUMN {column} {definition}"))
        elif dialect == "sqlite":
            # Keep existing server deployments bootable while their SQLite data is
            # being migrated to MySQL. SQLite has no SHOW COLUMNS equivalent.
            tables = {
                "derived_product_recommendations": derived_columns,
                "fm_products": fm_columns,
                "model_configs": model_columns,
                "users": user_columns,
                "user_search_recommendations": search_result_columns,
            }
            for table, columns in tables.items():
                existing = {
                    row[1]
                    for row in conn.execute(text(f"PRAGMA table_info({table})"))
                }
                for column, definition in columns.items():
                    if column not in existing:
                        conn.execute(
                            text(
                                f"ALTER TABLE {table} "
                                f"ADD COLUMN {column} {definition}"
                            )
                        )
        else:
            raise RuntimeError(f"Unsupported database dialect: {dialect}")


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
