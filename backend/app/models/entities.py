from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    model_type: Mapped[str] = mapped_column(String(64), default="general", index=True)
    base_url: Mapped[str] = mapped_column(String(255), default="")
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(Text, default="")


class ThirdPartyConfig(Base, TimestampMixin):
    __tablename__ = "third_party_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_name: Mapped[str] = mapped_column(String(128))
    service_type: Mapped[str] = mapped_column(String(64), index=True)
    api_base_url: Mapped[str] = mapped_column(String(255), default="")
    access_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    secret_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    db_host: Mapped[str] = mapped_column(String(128), default="")
    db_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_name: Mapped[str] = mapped_column(String(128), default="")
    db_user: Mapped[str] = mapped_column(String(128), default="")
    db_password_encrypted: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(Text, default="")


class SelectionAttribute(Base, TimestampMixin):
    __tablename__ = "selection_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attribute_name: Mapped[str] = mapped_column(String(128))
    attribute_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    attribute_type: Mapped[str] = mapped_column(String(64), default="other")
    description: Mapped[str] = mapped_column(Text, default="")
    default_weight: Mapped[float] = mapped_column(Float, default=1.0)
    current_weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_system: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FmProduct(Base, TimestampMixin):
    __tablename__ = "fm_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fm_product_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(32), default="JP")
    platform: Mapped[str] = mapped_column(String(32), default="TikTok")
    list_type: Mapped[str] = mapped_column(String(32), default="hot")
    title: Mapped[str] = mapped_column(String(512))
    image_url: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="JPY")
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    rank_no: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(128), default="")
    shop_name: Mapped[str] = mapped_column(String(255), default="")
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(Text, default="")
    data_date: Mapped[str] = mapped_column(String(32), default="")
    raw_data: Mapped[str] = mapped_column(Text, default="{}")

    derived_products: Mapped[list["DerivedProductRecommendation"]] = relationship(back_populates="source_product")


class AiPromptTemplate(Base, TimestampMixin):
    __tablename__ = "ai_prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prompt_name: Mapped[str] = mapped_column(String(128))
    prompt_content: Mapped[str] = mapped_column(Text, default="")
    output_schema: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(Text, default="")


class TaskExecution(Base, TimestampMixin):
    __tablename__ = "task_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    task_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    trigger_source: Mapped[str] = mapped_column(String(64), default="api")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    result_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelCallLog(Base, TimestampMixin):
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    model_config_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    model_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)
    response_chars: Mapped[int] = mapped_column(Integer, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    request_preview: Mapped[str] = mapped_column(Text, default="")
    response_preview: Mapped[str] = mapped_column(Text, default="")


class DerivedProductRecommendation(Base, TimestampMixin):
    __tablename__ = "derived_product_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    family_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_product_id: Mapped[int] = mapped_column(ForeignKey("fm_products.id"), index=True)
    derived_title: Mapped[str] = mapped_column(String(255))
    derived_description: Mapped[str] = mapped_column(Text, default="")
    recommendation_reason: Mapped[str] = mapped_column(Text, default="")
    target_audience: Mapped[str] = mapped_column(String(255), default="")
    usage_scene: Mapped[str] = mapped_column(String(255), default="")
    suggested_price_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_keywords: Mapped[str] = mapped_column(String(512), default="")
    risk_notes: Mapped[str] = mapped_column(Text, default="")
    analysis_report: Mapped[str] = mapped_column(Text, default="{}")
    source_search_keywords: Mapped[str] = mapped_column(Text, default="[]")
    match_tags: Mapped[str] = mapped_column(Text, default="[]")
    prompt_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str] = mapped_column(String(128), default="")
    ai_score: Mapped[float] = mapped_column(Float, default=0)
    weighted_score: Mapped[float] = mapped_column(Float, default=0)
    supplier_search_status: Mapped[str] = mapped_column(String(32), default="not_searched")
    supplier_product_id: Mapped[str] = mapped_column(String(128), default="")
    supplier_title: Mapped[str] = mapped_column(String(512), default="")
    supplier_image_url: Mapped[str] = mapped_column(Text, default="")
    supplier_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    supplier_sales_count: Mapped[int] = mapped_column(Integer, default=0)
    supplier_shop_name: Mapped[str] = mapped_column(String(255), default="")
    supplier_source_url: Mapped[str] = mapped_column(Text, default="")
    supplier_match_score: Mapped[float] = mapped_column(Float, default=0)
    supplier_match_report: Mapped[str] = mapped_column(Text, default="{}")
    supplier_raw_data: Mapped[str] = mapped_column(Text, default="{}")
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    source_product: Mapped[FmProduct] = relationship(back_populates="derived_products")
    attributes: Mapped[list["DerivedProductAttributeScore"]] = relationship(back_populates="recommendation")


class ProductFamily(Base, TimestampMixin):
    __tablename__ = "product_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    family_group: Mapped[str] = mapped_column(String(128), index=True)
    family_variant: Mapped[str] = mapped_column(String(128), default="")
    family_name: Mapped[str] = mapped_column(String(255))
    category_path: Mapped[str] = mapped_column(String(255), default="")
    normalized_keywords: Mapped[str] = mapped_column(Text, default="[]")
    match_rule: Mapped[str] = mapped_column(Text, default="")


class ProductFamilyDimensionWeight(Base, TimestampMixin):
    __tablename__ = "product_family_dimension_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("product_families.id"), index=True)
    dimension_code: Mapped[str] = mapped_column(String(64), index=True)
    dimension_name: Mapped[str] = mapped_column(String(128))
    weight_percent: Mapped[float] = mapped_column(Float, default=12.5)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)
    approve_count: Mapped[int] = mapped_column(Integer, default=0)
    total_review_count: Mapped[int] = mapped_column(Integer, default=0)

    family: Mapped[ProductFamily] = relationship()


class DerivedProductDimensionReport(Base, TimestampMixin):
    __tablename__ = "derived_product_dimension_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("derived_product_recommendations.id"), index=True)
    family_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    dimension_code: Mapped[str] = mapped_column(String(64), index=True)
    dimension_name: Mapped[str] = mapped_column(String(128))
    rating_level: Mapped[str] = mapped_column(String(64), default="")
    analysis_content: Mapped[str] = mapped_column(Text, default="")
    weight_percent_snapshot: Mapped[float] = mapped_column(Float, default=12.5)


class DerivedProductAttributeScore(Base, TimestampMixin):
    __tablename__ = "derived_product_attribute_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_product_id: Mapped[int] = mapped_column(ForeignKey("fm_products.id"), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("derived_product_recommendations.id"), index=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("selection_attributes.id"), index=True)
    ai_score: Mapped[float] = mapped_column(Float, default=0)
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    teacher_result: Mapped[str] = mapped_column(String(32), default="neutral")
    teacher_comment: Mapped[str] = mapped_column(Text, default="")

    recommendation: Mapped[DerivedProductRecommendation] = relationship(back_populates="attributes")
    attribute: Mapped[SelectionAttribute] = relationship()


class TeacherReviewRecord(Base):
    __tablename__ = "teacher_review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_product_id: Mapped[int] = mapped_column(ForeignKey("fm_products.id"), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("derived_product_recommendations.id"), index=True)
    review_result: Mapped[str] = mapped_column(String(32))
    selected_attribute_ids: Mapped[str] = mapped_column(Text, default="[]")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    review_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyRecommendation(Base):
    __tablename__ = "daily_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_date: Mapped[str] = mapped_column(String(32))
    source_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    reason_summary: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FastMossSyncLog(Base):
    __tablename__ = "fastmoss_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_date: Mapped[str] = mapped_column(String(32), default="")
    page: Mapped[int] = mapped_column(Integer, default=1)
    pagesize: Mapped[int] = mapped_column(Integer, default=20)
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    synced_count: Mapped[int] = mapped_column(Integer, default=0)
    translation_success_count: Mapped[int] = mapped_column(Integer, default=0)
    translation_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    request_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    response_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
