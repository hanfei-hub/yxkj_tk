from __future__ import annotations

from datetime import date, datetime
from itertools import count

from app.core.security import hash_password


_attribute_id = count(11)
_review_id = count(1)

users = [
    {
        "id": 1,
        "username": "admin",
        "password_hash": hash_password("admin123"),
        "real_name": "系统管理员",
        "role": "admin",
        "status": 1,
        "last_login_at": None,
        "created_at": "2026-07-07 10:00:00",
    },
    {
        "id": 2,
        "username": "teacher",
        "password_hash": hash_password("teacher123"),
        "real_name": "选品老师",
        "role": "teacher",
        "status": 1,
        "last_login_at": None,
        "created_at": "2026-07-07 10:00:00",
    },
    {
        "id": 3,
        "username": "student",
        "password_hash": hash_password("student123"),
        "real_name": "学生账号",
        "role": "student",
        "status": 1,
        "last_login_at": None,
        "created_at": "2026-07-07 10:00:00",
    },
]

model_configs = [
    {
        "id": 1,
        "config_name": "默认兼容模型",
        "provider": "custom",
        "base_url": "https://api.example.com/v1",
        "model_name": "configurable-chat-model",
        "temperature": 0.7,
        "max_tokens": 2000,
        "is_default": 1,
        "status": 1,
        "remark": "MVP 占位配置，后续在管理员页面替换为真实模型。",
    }
]

third_party_configs = [
    {
        "id": 1,
        "config_name": "FastMoss 日本区 API",
        "service_type": "fastmoss",
        "api_base_url": "https://api.fastmoss.example",
        "status": 1,
        "remark": "已有 API 权限，待录入真实密钥。",
    },
    {
        "id": 2,
        "config_name": "1688 寻源适配器",
        "service_type": "1688_api",
        "api_base_url": "",
        "status": 0,
        "remark": "第三方形式待定，支持 API 或 MySQL。",
    },
]

selection_attributes = [
    {"id": 1, "attribute_name": "周期性", "attribute_code": "periodicity", "attribute_type": "scene", "description": "是否存在季节、节日、复购或周期消费关系。", "default_weight": 1.0, "current_weight": 1.0, "is_system": 1, "status": 1},
    {"id": 2, "attribute_name": "使用场景", "attribute_code": "usage_scene", "attribute_type": "scene", "description": "是否共享或延展原商品使用场景。", "default_weight": 1.2, "current_weight": 1.2, "is_system": 1, "status": 1},
    {"id": 3, "attribute_name": "同属新奇特", "attribute_code": "novelty", "attribute_type": "novelty", "description": "是否具备短视频可展示的新奇特属性。", "default_weight": 1.3, "current_weight": 1.3, "is_system": 1, "status": 1},
    {"id": 4, "attribute_name": "人群匹配", "attribute_code": "crowd_match", "attribute_type": "crowd", "description": "是否面向相似或可迁移用户群。", "default_weight": 1.4, "current_weight": 1.4, "is_system": 1, "status": 1},
    {"id": 5, "attribute_name": "价格带匹配", "attribute_code": "price_match", "attribute_type": "price", "description": "是否符合日本 TikTok 电商常见价格带。", "default_weight": 1.0, "current_weight": 1.0, "is_system": 1, "status": 1},
    {"id": 6, "attribute_name": "内容传播性", "attribute_code": "content_viral", "attribute_type": "novelty", "description": "是否适合短视频展示和种草。", "default_weight": 1.5, "current_weight": 1.5, "is_system": 1, "status": 1},
    {"id": 7, "attribute_name": "物流友好度", "attribute_code": "logistics", "attribute_type": "logistics", "description": "体积、重量、破损风险是否适合跨境。", "default_weight": 0.8, "current_weight": 0.8, "is_system": 1, "status": 1},
    {"id": 8, "attribute_name": "侵权风险", "attribute_code": "ip_risk", "attribute_type": "risk", "description": "是否存在品牌、外观、专利等风险。", "default_weight": 1.6, "current_weight": 1.6, "is_system": 1, "status": 1},
    {"id": 9, "attribute_name": "供应链稳定性", "attribute_code": "supply_stability", "attribute_type": "supply", "description": "是否容易稳定寻源和持续供货。", "default_weight": 1.0, "current_weight": 1.0, "is_system": 1, "status": 1},
    {"id": 10, "attribute_name": "日本市场匹配度", "attribute_code": "jp_market_fit", "attribute_type": "crowd", "description": "是否符合日本地区审美、使用习惯和消费偏好。", "default_weight": 1.5, "current_weight": 1.5, "is_system": 1, "status": 1},
]

products = [
    {
        "id": 101,
        "title": "便携式猫咪自动饮水器",
        "image_url": "",
        "price": 2980,
        "currency": "JPY",
        "sales_count": 18420,
        "rank_no": 1,
        "category": "宠物用品",
        "comment_count": 862,
        "data_date": str(date.today()),
        "derived_count": 3,
        "pending_count": 2,
        "reviewed_count": 1,
    },
    {
        "id": 102,
        "title": "厨房水槽防溅伸缩挡板",
        "image_url": "",
        "price": 1680,
        "currency": "JPY",
        "sales_count": 12680,
        "rank_no": 2,
        "category": "家居厨房",
        "comment_count": 493,
        "data_date": str(date.today()),
        "derived_count": 2,
        "pending_count": 2,
        "reviewed_count": 0,
    },
    {
        "id": 103,
        "title": "桌面迷你加湿香薰灯",
        "image_url": "",
        "price": 2280,
        "currency": "JPY",
        "sales_count": 9780,
        "rank_no": 3,
        "category": "生活小家电",
        "comment_count": 331,
        "data_date": str(date.today()),
        "derived_count": 2,
        "pending_count": 1,
        "reviewed_count": 1,
    },
]

derived_products = [
    {
        "id": 1001,
        "source_product_id": 101,
        "derived_title": "猫咪循环过滤饮水机滤芯套装",
        "derived_description": "围绕自动饮水器形成复购型耗材，适合做低客单补充品。",
        "recommendation_reason": "原商品评论集中提到清洁、滤芯更换和水质问题，耗材复购逻辑明确。",
        "target_audience": "养猫家庭、重视宠物健康的年轻用户",
        "usage_scene": "宠物饮水维护、日常补充耗材",
        "risk_notes": "需确认滤芯规格兼容性，避免品牌侵权描述。",
        "ai_score": 88,
        "weighted_score": 90,
        "supplier_search_status": "not_searched",
        "review_status": "pending",
        "attributes": [
            {"attribute_id": 1, "attribute_name": "周期性", "ai_score": 92, "ai_reason": "滤芯具备固定更换周期。"},
            {"attribute_id": 2, "attribute_name": "使用场景", "ai_score": 95, "ai_reason": "与原商品完全处于同一使用场景。"},
            {"attribute_id": 4, "attribute_name": "人群匹配", "ai_score": 90, "ai_reason": "同样面向养猫用户。"},
        ],
    },
    {
        "id": 1002,
        "source_product_id": 101,
        "derived_title": "宠物饮水区防滑吸水垫",
        "derived_description": "解决饮水器周边湿滑、打翻和清洁问题。",
        "recommendation_reason": "评论中多次出现地面湿、清理麻烦，场景痛点明确。",
        "target_audience": "养猫养狗家庭",
        "usage_scene": "宠物饮水区清洁和防滑",
        "risk_notes": "同质化较强，需要图案、尺寸或材质差异化。",
        "ai_score": 81,
        "weighted_score": 83,
        "supplier_search_status": "has_result",
        "review_status": "pending",
        "attributes": [
            {"attribute_id": 2, "attribute_name": "使用场景", "ai_score": 88, "ai_reason": "围绕饮水器周边使用。"},
            {"attribute_id": 4, "attribute_name": "人群匹配", "ai_score": 86, "ai_reason": "目标人群高度重合。"},
            {"attribute_id": 6, "attribute_name": "内容传播性", "ai_score": 72, "ai_reason": "清洁对比内容可展示，但新奇程度一般。"},
        ],
    },
    {
        "id": 1003,
        "source_product_id": 101,
        "derived_title": "猫咪透明太空舱背包",
        "derived_description": "宠物外出携带用品，视觉强但和原商品场景跨度较大。",
        "recommendation_reason": "同为宠物人群，短视频展示强，但不属于原饮水场景延展。",
        "target_audience": "爱晒宠、经常带宠物外出的用户",
        "usage_scene": "宠物外出",
        "risk_notes": "体积较大，物流成本和售后风险较高。",
        "ai_score": 69,
        "weighted_score": 64,
        "supplier_search_status": "not_searched",
        "review_status": "approved",
        "attributes": [
            {"attribute_id": 3, "attribute_name": "同属新奇特", "ai_score": 78, "ai_reason": "视觉展示较强。"},
            {"attribute_id": 4, "attribute_name": "人群匹配", "ai_score": 80, "ai_reason": "同样面向宠物用户。"},
            {"attribute_id": 7, "attribute_name": "物流友好度", "ai_score": 45, "ai_reason": "体积偏大。"},
        ],
    },
    {
        "id": 2001,
        "source_product_id": 102,
        "derived_title": "厨房台面吸水速干垫",
        "derived_description": "水槽周边收纳与防潮清洁衍生品。",
        "recommendation_reason": "和防溅挡板处于同一厨房清洁场景，容易组合销售。",
        "target_audience": "小户型家庭、厨房收纳用户",
        "usage_scene": "厨房水槽清洁",
        "risk_notes": "需注意材质差异化。",
        "ai_score": 84,
        "weighted_score": 85,
        "supplier_search_status": "has_result",
        "review_status": "pending",
        "attributes": [
            {"attribute_id": 2, "attribute_name": "使用场景", "ai_score": 92, "ai_reason": "同一厨房水槽场景。"},
            {"attribute_id": 5, "attribute_name": "价格带匹配", "ai_score": 86, "ai_reason": "低客单易成交。"},
            {"attribute_id": 7, "attribute_name": "物流友好度", "ai_score": 90, "ai_reason": "轻小件。"},
        ],
    },
    {
        "id": 3001,
        "source_product_id": 103,
        "derived_title": "桌面氛围夜灯香薰片",
        "derived_description": "围绕桌面香薰灯做低价耗材和氛围配件。",
        "recommendation_reason": "具备复购和场景搭配关系，适合用氛围感内容展示。",
        "target_audience": "学生、办公室人群、独居女性",
        "usage_scene": "桌面办公、睡前放松",
        "risk_notes": "香薰类需要关注成分合规和运输限制。",
        "ai_score": 86,
        "weighted_score": 87,
        "supplier_search_status": "not_searched",
        "review_status": "pending",
        "attributes": [
            {"attribute_id": 1, "attribute_name": "周期性", "ai_score": 85, "ai_reason": "香薰片有耗材复购。"},
            {"attribute_id": 2, "attribute_name": "使用场景", "ai_score": 90, "ai_reason": "同一桌面氛围场景。"},
            {"attribute_id": 6, "attribute_name": "内容传播性", "ai_score": 84, "ai_reason": "氛围变化适合短视频展示。"},
        ],
    },
]

review_records = []

daily_recommendations = [
    {
        "id": index + 1,
        "title": item["derived_title"],
        "image_url": "",
        "price": 980 + index * 180,
        "sales_count": 3000 + index * 420,
        "reason_summary": item["recommendation_reason"],
        "sort_order": index + 1,
    }
    for index, item in enumerate((derived_products * 2)[:10])
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_user(username: str) -> dict | None:
    return next((user for user in users if user["username"] == username), None)


def find_user_by_id(user_id: int) -> dict | None:
    return next((user for user in users if user["id"] == user_id), None)


def public_user(user: dict) -> dict:
    return {key: value for key, value in user.items() if key != "password_hash"}


def next_attribute_id() -> int:
    return next(_attribute_id)


def next_review_id() -> int:
    return next(_review_id)
