from __future__ import annotations

import sys
from io import BytesIO
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPixmap
from PIL import Image, ImageOps
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from api.client import ApiClient, ApiError


MOCK_USERS = {
    "admin": {"password": "admin123", "user": {"id": 1, "username": "admin", "real_name": "系统管理员", "role": "admin"}},
    "teacher": {"password": "teacher123", "user": {"id": 2, "username": "teacher", "real_name": "选品老师", "role": "teacher"}},
    "student": {"password": "student123", "user": {"id": 3, "username": "student", "real_name": "学生账号", "role": "student"}},
}

MOCK_PRODUCTS = [
    {"id": 101, "title": "便携式猫咪自动饮水器", "price": 2980, "currency": "JPY", "sales_count": 18420, "rank_no": 1, "category": "宠物用品", "comment_count": 862, "derived_count": 3, "pending_count": 2, "reviewed_count": 1},
    {"id": 102, "title": "厨房水槽防溅伸缩挡板", "price": 1680, "currency": "JPY", "sales_count": 12680, "rank_no": 2, "category": "家居厨房", "comment_count": 493, "derived_count": 2, "pending_count": 2, "reviewed_count": 0},
    {"id": 103, "title": "桌面迷你加湿香薰灯", "price": 2280, "currency": "JPY", "sales_count": 9780, "rank_no": 3, "category": "生活小家电", "comment_count": 331, "derived_count": 2, "pending_count": 1, "reviewed_count": 1},
]

FASTMOSS_REAL_PRODUCTS = [
    {"id": 9001, "fm_product_id": "1736344738303673967", "title": "umai studioオレンジスクイーズ  付属品を同封します", "price": 2157, "currency": "JPY", "sales_count": 127, "rank_no": 1, "category": "Toys & Hobbies / Classic & Novelty Toys / Stress Relief Toys", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 95, "rating": 4.8},
    {"id": 9002, "fm_product_id": "1736312872437122409", "title": "【KIIRO】2026年新作 無地レースの9分丈パンツ。薄手で軽やか、ゆったりシルエットで細見えするワイドパンツ。", "price": 2317, "currency": "JPY", "sales_count": 86, "rank_no": 2, "category": "Womenswear & Underwear / Women's Bottoms / Trousers", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 94, "rating": 4.7},
    {"id": 9003, "fm_product_id": "1736328707754198733", "title": "人工水晶 - 人工水晶の置物 - 人工水晶のペンダント - 人工水晶のアクセサリー", "price": 11, "currency": "JPY", "sales_count": 79, "rank_no": 3, "category": "Jewelry Accessories & Derivatives / Natural Crystal / Natural Crystal Decorations", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 93, "rating": 4.6},
    {"id": 9004, "fm_product_id": "1736333423317387249", "title": "TOPTOY MayMeiメイメイ もふもふポケット ぬいぐるみブラインドボックス", "price": 4840, "currency": "JPY", "sales_count": 75, "rank_no": 4, "category": "Toys & Hobbies / Dolls & Stuffed Toys / Dolls", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 92, "rating": 4.5},
    {"id": 9005, "fm_product_id": "1736342702570308889", "title": "DIYやカーメンテに 10mmスリープ ソケット 3/8インチアダプターき ユニバーサルソケットレンチ", "price": 2422, "currency": "JPY", "sales_count": 67, "rank_no": 5, "category": "Tools & Hardware / Hand Tools / Wrenches", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 91, "rating": 4.9},
    {"id": 9006, "fm_product_id": "1736334486273361905", "title": "TOPTOY Sanrio サンリオキャラクターズ 癒し空間シリーズ フィギュア ブラインドボックス", "price": 1760, "currency": "JPY", "sales_count": 54, "rank_no": 6, "category": "Toys & Hobbies / Classic & Novelty Toys / Action & Toy Figures", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 90, "rating": 4.8},
    {"id": 9007, "fm_product_id": "1736296144362244093", "title": "菩提算盤シリーズビーズ(2)    9色", "price": 599, "currency": "JPY", "sales_count": 40, "rank_no": 7, "category": "Fashion Accessories / Costume Jewelry & Accessories / Bracelets & Bangles", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 89, "rating": 4.7},
    {"id": 9008, "fm_product_id": "1736281150610507773", "title": "菩提算盤シリーズビーズ    9色", "price": 599, "currency": "JPY", "sales_count": 38, "rank_no": 8, "category": "Fashion Accessories / Costume Jewelry & Accessories / Bracelets & Bangles", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 88, "rating": 4.6},
    {"id": 9009, "fm_product_id": "1736345374207936509", "title": "8mm 【満天星シリーズ】キラキラ花玉ビーズ 16色", "price": 399, "currency": "JPY", "sales_count": 33, "rank_no": 9, "category": "Fashion Accessories / Costume Jewelry & Accessories / Bracelets & Bangles", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 87, "rating": 4.5},
    {"id": 9010, "fm_product_id": "1736347038588962584", "title": "【巧可熊 6月21日新作】ストレス解消 おもちゃ 手作りスクイーズおもちゃ  デコ置物", "price": 2668, "currency": "JPY", "sales_count": 30, "rank_no": 10, "category": "Home Supplies / Home Decor / Statues & Figurines", "comment_count": 0, "data_date": "2026-07-03", "derived_count": 0, "pending_count": 0, "reviewed_count": 0, "ai_score": 86, "rating": 4.9},
]
FASTMOSS_IMAGE_URLS = {
    "1736344738303673967": "https://s.500fd.com/tt_product/7a48a0c627464fa1b0e647373334eb79~tplv-aphluv4xwc-crop-webp:1440:1784.webp",
    "1736312872437122409": "https://s.500fd.com/tt_product/3081b93925bb407f8c693a8f3d475244~tplv-aphluv4xwc-crop-webp:1254:1254.webp",
    "1736328707754198733": "https://s.500fd.com/tt_product/d1da3950d43d4bb881987cf2649020ae~tplv-aphluv4xwc-crop-webp:1256:1464.webp",
    "1736333423317387249": "https://s.500fd.com/tt_product/32faa09f324d4e858b9112188a01eeb9~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
    "1736342702570308889": "https://s.500fd.com/tt_product/f89cb2cf9b07406fbfecd19cb40d458e~tplv-aphluv4xwc-crop-webp:1200:1200.webp",
    "1736334486273361905": "https://s.500fd.com/tt_product/e6dc41b13a3f43ba81482f4b170bb7f3~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
    "1736296144362244093": "https://s.500fd.com/tt_product/4b6c27d4da764a0aae7839b1fb2666bc~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
    "1736281150610507773": "https://s.500fd.com/tt_product/2143be3ab7f2444ab5153437af1ee3a7~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
    "1736345374207936509": "https://s.500fd.com/tt_product/9d32085eb8fd4d8a8d0cd0e3c7f71710~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
    "1736347038588962584": "https://s.500fd.com/tt_product/297b4f0f4aea4f9498c1726313606ca5~tplv-aphluv4xwc-crop-webp:1440:1440.webp",
}
for product in FASTMOSS_REAL_PRODUCTS:
    product["image_url"] = FASTMOSS_IMAGE_URLS.get(str(product.get("fm_product_id")), "")
MOCK_PRODUCTS = FASTMOSS_REAL_PRODUCTS

MOCK_ATTRIBUTES = [
    {"id": 1, "attribute_name": "周期性", "attribute_type": "scene", "current_weight": 1.0},
    {"id": 2, "attribute_name": "使用场景", "attribute_type": "scene", "current_weight": 1.2},
    {"id": 3, "attribute_name": "同属新奇特", "attribute_type": "novelty", "current_weight": 1.3},
    {"id": 4, "attribute_name": "人群匹配", "attribute_type": "crowd", "current_weight": 1.4},
    {"id": 5, "attribute_name": "价格带匹配", "attribute_type": "price", "current_weight": 1.0},
    {"id": 6, "attribute_name": "内容传播性", "attribute_type": "novelty", "current_weight": 1.5},
    {"id": 7, "attribute_name": "物流友好度", "attribute_type": "logistics", "current_weight": 0.8},
    {"id": 8, "attribute_name": "侵权风险", "attribute_type": "risk", "current_weight": 1.6},
]

MOCK_DERIVED = {
    101: [
        {"id": 1001, "derived_title": "猫咪循环过滤饮水机滤芯套装", "target_audience": "养猫家庭", "usage_scene": "宠物饮水维护", "recommendation_reason": "评论集中提到清洁和滤芯更换，耗材复购逻辑明确。", "risk_notes": "需确认规格兼容性。", "ai_score": 88, "weighted_score": 90, "review_status": "pending", "attributes": [{"attribute_name": "周期性", "ai_score": 92}, {"attribute_name": "使用场景", "ai_score": 95}, {"attribute_name": "人群匹配", "ai_score": 90}]},
        {"id": 1002, "derived_title": "宠物饮水区防滑吸水垫", "target_audience": "养宠家庭", "usage_scene": "宠物饮水区清洁", "recommendation_reason": "解决地面湿滑和清理麻烦。", "risk_notes": "同质化较强。", "ai_score": 81, "weighted_score": 83, "review_status": "pending", "attributes": [{"attribute_name": "使用场景", "ai_score": 88}, {"attribute_name": "人群匹配", "ai_score": 86}, {"attribute_name": "内容传播性", "ai_score": 72}]},
    ],
    102: [
        {"id": 2001, "derived_title": "厨房台面吸水速干垫", "target_audience": "小户型家庭", "usage_scene": "厨房水槽清洁", "recommendation_reason": "和防溅挡板处于同一厨房清洁场景。", "risk_notes": "注意材质差异化。", "ai_score": 84, "weighted_score": 85, "review_status": "pending", "attributes": [{"attribute_name": "使用场景", "ai_score": 92}, {"attribute_name": "价格带匹配", "ai_score": 86}, {"attribute_name": "物流友好度", "ai_score": 90}]},
    ],
    103: [
        {"id": 3001, "derived_title": "桌面氛围夜灯香薰片", "target_audience": "学生、办公室人群", "usage_scene": "桌面办公、睡前放松", "recommendation_reason": "具备复购和场景搭配关系。", "risk_notes": "关注成分合规和运输限制。", "ai_score": 86, "weighted_score": 87, "review_status": "pending", "attributes": [{"attribute_name": "周期性", "ai_score": 85}, {"attribute_name": "使用场景", "ai_score": 90}, {"attribute_name": "内容传播性", "ai_score": 84}]},
    ],
}


def build_demo_derived_products(product: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(product.get("title") or "FastMoss 商品")
    category = str(product.get("category") or "日本新品榜")
    base_id = int(product.get("id") or 9000) * 10
    return [
        {
            "id": base_id + 1,
            "derived_title": f"{title} 关联补充装/配件",
            "target_audience": "已被原商品吸引的日本用户",
            "usage_scene": "同一使用场景下的加购和复购",
            "recommendation_reason": f"原商品来自 FastMoss 日本新品榜，类目为 {category}，可围绕配件、耗材和组合套装扩展。",
            "risk_notes": "需进一步确认 1688 供货稳定性、侵权风险和物流体积。",
            "ai_score": int(product.get("ai_score") or 88),
            "weighted_score": int(product.get("ai_score") or 88),
            "review_status": "pending",
            "attributes": [
                {"attribute_name": "使用场景", "ai_score": 90},
                {"attribute_name": "人群匹配", "ai_score": 88},
                {"attribute_name": "同属新奇特", "ai_score": 84},
            ],
        },
        {
            "id": base_id + 2,
            "derived_title": f"{title} 同类低价替代款",
            "target_audience": "价格敏感型消费者",
            "usage_scene": "同类目测款和价格带覆盖",
            "recommendation_reason": "用低价替代款验证同一需求是否具备更高转化空间，适合作为衍生选品候选。",
            "risk_notes": "注意同质化竞争和素材差异化。",
            "ai_score": 82,
            "weighted_score": 84,
            "review_status": "pending",
            "attributes": [
                {"attribute_name": "价格带匹配", "ai_score": 88},
                {"attribute_name": "物流友好度", "ai_score": 82},
                {"attribute_name": "内容传播性", "ai_score": 80},
            ],
        },
    ]


class DataGateway:
    def __init__(self) -> None:
        self.client = ApiClient()
        self.offline = False
        self.user: dict[str, Any] | None = None
        self.offline_model_configs = [
            {
                "id": 1,
                "config_name": "默认兼容模型",
                "provider": "custom",
                "base_url": "https://api.example.com/v1",
                "api_key_encrypted": "",
                "model_name": "configurable-chat-model",
                "temperature": 0.7,
                "max_tokens": 2000,
                "is_default": 1,
                "status": 1,
                "remark": "",
            }
        ]

    def login(self, username: str, password: str) -> dict[str, Any]:
        try:
            data = self.client.login(username, password)
            self.offline = False
            self.user = data["user"]
            return self.user
        except ApiError:
            demo = MOCK_USERS.get(username)
            if not demo or demo["password"] != password:
                raise
            self.offline = True
            self.user = demo["user"]
            return self.user

    def hot_products(self) -> list[dict[str, Any]]:
        if self.offline:
            return MOCK_PRODUCTS
        return self.client.get("/api/products/hot")

    def daily_recommendations(self) -> list[dict[str, Any]]:
        if self.offline:
            return [
                {
                    "title": item["title"],
                    "price": item["price"],
                    "sales_count": item["sales_count"],
                    "reason_summary": f"FastMoss 日本新品榜 {item['data_date']}，跨境=是，全托管=否。",
                }
                for item in FASTMOSS_REAL_PRODUCTS
            ][:10]
        return self.client.get("/api/daily-recommendations")

    def derived_products(self, product_id: int) -> list[dict[str, Any]]:
        if self.offline:
            existing = MOCK_DERIVED.get(product_id)
            if existing:
                return existing
            product = next((item for item in FASTMOSS_REAL_PRODUCTS if int(item["id"]) == int(product_id)), None)
            if not product:
                return []
            return build_demo_derived_products(product)
        return self.client.get(f"/api/teacher/products/{product_id}/derived-products")

    def generate_derived_products(self, product_id: int) -> dict[str, Any]:
        if self.offline:
            product = next((item for item in FASTMOSS_REAL_PRODUCTS if int(item["id"]) == int(product_id)), None)
            items = build_demo_derived_products(product or {"id": product_id, "title": "演示商品", "category": "演示类目"})
            MOCK_DERIVED[product_id] = items
            return {"ok": True, "model_used": False, "count": len(items), "items": items}
        return self.client.post(f"/api/ai/products/{product_id}/generate-derived")

    def attributes(self) -> list[dict[str, Any]]:
        if self.offline:
            return MOCK_ATTRIBUTES
        if self.user and self.user["role"] == "admin":
            return self.client.get("/api/admin/selection-attributes")
        return self.client.get("/api/selection-attributes")

    def users(self) -> list[dict[str, Any]]:
        if self.offline:
            return [item["user"] | {"status": 1, "last_login_at": "-", "created_at": "-"} for item in MOCK_USERS.values()]
        return self.client.get("/api/admin/users")

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            user = {"id": len(MOCK_USERS) + 1, **payload, "status": 1, "last_login_at": "-"}
            MOCK_USERS[payload["username"]] = {"password": payload.get("password", "123456"), "user": user}
            return user
        return self.client.post("/api/admin/users", payload)

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            return payload | {"id": user_id}
        return self.client.put(f"/api/admin/users/{user_id}", payload)

    def set_user_status(self, user_id: int, status: int) -> dict[str, Any]:
        if self.offline:
            return {"id": user_id, "status": status}
        return self.client.patch(f"/api/admin/users/{user_id}/status", {"status": status})

    def model_configs(self) -> list[dict[str, Any]]:
        if self.offline:
            return self.offline_model_configs
        return self.client.get("/api/admin/model-configs")

    def save_model_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        if self.offline:
            if config_id:
                for index, item in enumerate(self.offline_model_configs):
                    if int(item.get("id") or 0) == int(config_id):
                        self.offline_model_configs[index] = item | payload | {"id": config_id}
                        return self.offline_model_configs[index]
            item = payload | {"id": max([int(i.get("id") or 0) for i in self.offline_model_configs] or [0]) + 1}
            if int(item.get("is_default") or 0):
                for existing in self.offline_model_configs:
                    existing["is_default"] = 0
            self.offline_model_configs.append(item)
            return item
        if config_id:
            return self.client.put(f"/api/admin/model-configs/{config_id}", payload)
        return self.client.post("/api/admin/model-configs", payload)

    def set_model_status(self, config_id: int, status: int) -> dict[str, Any]:
        if self.offline:
            for item in self.offline_model_configs:
                if int(item.get("id") or 0) == int(config_id):
                    item["status"] = status
                    return item
            return {"id": config_id, "status": status}
        return self.client.patch(f"/api/admin/model-configs/{config_id}/status", {"status": status})

    def set_default_model(self, config_id: int) -> dict[str, Any]:
        if self.offline:
            selected = {"id": config_id, "is_default": 1}
            for item in self.offline_model_configs:
                item["is_default"] = 1 if int(item.get("id") or 0) == int(config_id) else 0
                if item["is_default"]:
                    selected = item
            return selected
        return self.client.post(f"/api/admin/model-configs/{config_id}/default")

    def third_party_configs(self) -> list[dict[str, Any]]:
        if self.offline:
            return [{"config_name": "FastMoss 日本区 API", "service_type": "fastmoss", "status": 1}, {"config_name": "1688 寻源适配器", "service_type": "1688_api", "status": 0}]
        return self.client.get("/api/admin/third-party-configs")

    def save_third_party_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        if self.offline:
            return payload | {"id": config_id or 1}
        if config_id:
            return self.client.put(f"/api/admin/third-party-configs/{config_id}", payload)
        return self.client.post("/api/admin/third-party-configs", payload)

    def set_third_party_status(self, config_id: int, status: int) -> dict[str, Any]:
        if self.offline:
            return {"id": config_id, "status": status}
        return self.client.patch(f"/api/admin/third-party-configs/{config_id}/status", {"status": status})

    def sync_fastmoss_products(self) -> dict[str, Any]:
        if self.offline:
            return {"ok": False, "message": "当前为离线演示模式，请先启动本地后端。"}
        return self.client.post("/api/fastmoss/sync-products?page=1&pagesize=20")

    def ai_chat(self, message: str) -> str:
        if self.offline:
            return f"基于日本区趋势，建议围绕宠物耗材、厨房清洁、桌面氛围配件继续深挖。你的问题是：{message}"
        return self.client.post("/api/ai/chat-selection", {"message": message})["answer"]

    def save_attribute(self, payload: dict[str, Any], attribute_id: int | None = None) -> dict[str, Any]:
        if self.offline:
            return payload | {"id": attribute_id or len(MOCK_ATTRIBUTES) + 1}
        if attribute_id:
            return self.client.put(f"/api/admin/selection-attributes/{attribute_id}", payload)
        return self.client.post("/api/admin/selection-attributes", payload)

    def set_attribute_status(self, attribute_id: int, status: int) -> dict[str, Any]:
        if self.offline:
            return {"id": attribute_id, "status": status}
        return self.client.patch(f"/api/admin/selection-attributes/{attribute_id}/status", {"status": status})

    def approve(self, derived_id: int) -> None:
        if not self.offline:
            self.client.post(f"/api/teacher/derived-products/{derived_id}/approve")

    def reject(self, derived_id: int, attribute_ids: list[int], comment: str) -> None:
        if not self.offline:
            self.client.post(f"/api/teacher/derived-products/{derived_id}/reject", {"attribute_ids": attribute_ids, "review_comment": comment})

    def search_1688(self, keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if self.offline:
            return {"ok": False, "keyword": keyword, "items": []}
        return self.client.post("/api/suppliers/1688/search", {"keyword": keyword, "page": page, "page_size": page_size})

    def search_1688_for_derived(self, derived_id: int, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if self.offline:
            return {"ok": False, "items": []}
        return self.client.post(f"/api/suppliers/1688/derived-products/{derived_id}/search?page={page}&page_size={page_size}")


def make_title(text: str, subtitle: str = "") -> QWidget:
    box = QFrame()
    box.setObjectName("PageHeader")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(6)
    title = QLabel(text)
    title.setObjectName("PageTitle")
    layout.addWidget(title)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        layout.addWidget(sub)
    return box


def table(headers: list[str]) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.setWordWrap(False)
    widget.verticalHeader().setDefaultSectionSize(46)
    return widget


def fill_table(widget: QTableWidget, rows: list[list[Any]]) -> None:
    widget.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            widget.setItem(row_index, column_index, item)


def metric_card(title: str, value: str, note: str) -> QWidget:
    card = QFrame()
    card.setObjectName("MetricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("ProductMuted")
    value_label = QLabel(value)
    value_label.setObjectName("DashboardMetric")
    note_label = QLabel(note)
    note_label.setObjectName("Muted")
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    layout.addWidget(note_label)
    return card


class FormDialog(QDialog):
    def __init__(self, title: str, fields: list[tuple[str, str, str]], initial: dict[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, max(260, 90 + len(fields) * 48))
        self.inputs: dict[str, QLineEdit] = {}
        initial = initial or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        header = QLabel(title)
        header.setObjectName("CardTitle")
        layout.addWidget(header)
        for key, label, placeholder in fields:
            row = QHBoxLayout()
            row_label = QLabel(label)
            row_label.setMinimumWidth(110)
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setText(str(initial.get(key, "")))
            self.inputs[key] = edit
            row.addWidget(row_label)
            row.addWidget(edit, 1)
            layout.addLayout(row)
        actions = QHBoxLayout()
        cancel = QPushButton("取消")
        save = QPushButton("保存")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def data(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self.inputs.items()}


class LoginWindow(QWidget):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.setWindowTitle("TK 日本跨境智能选品系统")
        self.setMinimumSize(980, 640)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        hero = QFrame()
        hero.setObjectName("HeroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(52, 52, 52, 52)
        hero_layout.addStretch()
        brand = QLabel("TK 日本跨境\n智能选品系统")
        brand.setObjectName("HeroTitle")
        desc = QLabel("FastMoss 趋势数据、AI 衍生品生成、教师审核闭环和属性权重沉淀。")
        desc.setObjectName("HeroText")
        desc.setWordWrap(True)
        hero_layout.addWidget(brand)
        hero_layout.addSpacing(18)
        hero_layout.addWidget(desc)
        hero_layout.addStretch()

        form = QFrame()
        form.setObjectName("LoginPanel")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(54, 54, 54, 54)
        form_layout.addStretch()
        title = QLabel("登录")
        title.setObjectName("LoginTitle")
        hint = QLabel("演示账号：admin/admin123，teacher/teacher123，student/student123")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.username = QLineEdit()
        self.username.setPlaceholderText("账号")
        self.password = QLineEdit()
        self.password.setPlaceholderText("密码")
        self.password.setEchoMode(QLineEdit.Password)
        self.login_button = QPushButton("进入系统")
        self.login_button.clicked.connect(self.do_login)
        form_layout.addWidget(title)
        form_layout.addWidget(hint)
        form_layout.addSpacing(20)
        form_layout.addWidget(self.username)
        form_layout.addWidget(self.password)
        form_layout.addWidget(self.login_button)
        form_layout.addStretch()

        root.addWidget(hero, 5)
        root.addWidget(form, 4)

    def do_login(self) -> None:
        try:
            user = self.gateway.login(self.username.text().strip(), self.password.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "登录失败", f"账号或密码不正确，或后端不可用。\n{exc}")
            return
        self.main_window = MainWindow(self.gateway, user)
        self.main_window.show()
        self.close()


class LoginDialog(QDialog):
    def __init__(self, gateway: DataGateway, parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.user: dict[str, Any] | None = None
        self.setWindowTitle("用户登录")
        self.resize(420, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel("登录账号")
        title.setObjectName("LoginTitle")
        hint = QLabel("演示账号：admin/admin123，teacher/teacher123，student/student123")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        self.username = QLineEdit()
        self.username.setPlaceholderText("账号")
        self.password = QLineEdit()
        self.password.setPlaceholderText("密码")
        self.password.setEchoMode(QLineEdit.Password)

        actions = QHBoxLayout()
        cancel = QPushButton("取消")
        login = QPushButton("登录")
        cancel.clicked.connect(self.reject)
        login.clicked.connect(self.do_login)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(login)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addLayout(actions)

    def do_login(self) -> None:
        try:
            self.user = self.gateway.login(self.username.text().strip(), self.password.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "登录失败", f"账号或密码不正确，或后端不可用。\n{exc}")
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, gateway: DataGateway, user: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.gateway = gateway
        if user is None:
            self.gateway.offline = True
        self.user = user
        self.setWindowTitle("TK 日本跨境智能选品系统")
        self.setMinimumSize(1180, 760)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("SidePanel")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        brand_box = QFrame()
        brand_box.setObjectName("BrandBox")
        brand_layout = QVBoxLayout(brand_box)
        brand_layout.setContentsMargins(20, 22, 18, 18)
        brand_layout.setSpacing(6)
        brand = QLabel("🌐 TK跨境助手")
        brand.setObjectName("BrandTitle")
        brand_sub = QLabel("Japan TikTok Selection")
        brand_sub.setObjectName("BrandSub")
        brand_layout.addWidget(brand)
        brand_layout.addWidget(brand_sub)

        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(220)
        self.stack = QStackedWidget()

        self.user_label = QLabel()
        self.user_label.setObjectName("UserStatus")
        self.user_label.setWordWrap(True)
        self.login_button = QPushButton("登录")
        self.login_button.setObjectName("SideLoginButton")
        self.login_button.clicked.connect(self.open_login_dialog)

        user_box = QFrame()
        user_box.setObjectName("UserBox")
        user_layout = QVBoxLayout(user_box)
        user_layout.setContentsMargins(14, 12, 14, 14)
        user_layout.addWidget(self.user_label)
        user_layout.addWidget(self.login_button)

        sidebar_layout.addWidget(brand_box)
        sidebar_layout.addWidget(self.nav, 1)
        sidebar_layout.addWidget(user_box)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.pages: list[QWidget] = []
        self.setup_pages()
        self.update_login_status()
        self.nav.currentRowChanged.connect(self.on_page_changed)
        self.nav.setCurrentRow(0)

    def add_page(self, name: str, page: QWidget, icon: str = "") -> None:
        item = QListWidgetItem(name)
        if icon:
            item.setText(f"{icon}  {name}")
        item.setTextAlignment(Qt.AlignVCenter)
        self.nav.addItem(item)
        self.stack.addWidget(page)
        self.pages.append(page)

    def setup_pages(self) -> None:
        self.add_page("智能选品", StudentSelectionPage(self.gateway), "🏠")
        self.add_page("教师看板", TeacherDashboardPage(self.gateway), "📦")
        self.add_page("用户管理", AdminUsersPage(self.gateway), "👥")
        self.add_page("模型配置", SimpleConfigPage("模型配置", self.gateway.model_configs, ["配置名称", "服务商", "Base URL", "模型", "Key", "状态", "默认"], self.gateway, "model"), "🤖")
        self.add_page("第三方 API", SimpleConfigPage("第三方 API 配置", self.gateway.third_party_configs, ["配置名称", "服务类型", "状态"], self.gateway, "third"), "🔌")
        self.add_page("选品属性", AttributePage(self.gateway), "⚖️")
        self.add_page("主题皮肤", ThemePage(self.apply_theme), "🎨")

    def update_login_status(self) -> None:
        if self.user:
            mode = "本地演示" if self.gateway.offline else "后端在线"
            api_host = self.gateway.client.base_url.replace("http://", "").replace("https://", "")
            self.user_label.setText(f"当前用户\n{self.user.get('real_name')} / {self.user.get('role')}\n{mode}\n{api_host}")
            self.login_button.setText("切换登录")
            self.setWindowTitle(f"TK 日本跨境智能选品系统 - {self.user.get('real_name')}")
            return
        self.user_label.setText("当前用户\n未登录\n开发预览模式")
        self.login_button.setText("登录")
        self.setWindowTitle("TK 日本跨境智能选品系统 - 开发预览")

    def open_login_dialog(self) -> None:
        dialog = LoginDialog(self.gateway, self)
        if dialog.exec() == QDialog.Accepted and dialog.user:
            self.user = dialog.user
            self.update_login_status()
            for page in self.pages:
                if hasattr(page, "loaded"):
                    setattr(page, "loaded", False)
                refresh = getattr(page, "refresh", None)
                if callable(refresh):
                    refresh()
            self.on_page_changed(self.nav.currentRow())

    def on_page_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.pages):
            page = self.pages[index]
            activate = getattr(page, "activate", None)
            if callable(activate):
                activate()

    def apply_theme(self, theme_name: str) -> None:
        app = QApplication.instance()
        if app:
            apply_style(app, theme_name)


class Page(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 26, 28, 26)
        self.layout.setSpacing(14)


class AdminUsersPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.layout.addWidget(make_title("用户管理", "管理员可以管理老师、学生和管理员账号。"))
        action_bar = QFrame()
        action_bar.setObjectName("Toolbar")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(14, 12, 14, 12)
        add = QPushButton("新增用户")
        edit = QPushButton("编辑选中")
        toggle = QPushButton("启用/禁用")
        add.clicked.connect(self.add_user)
        edit.clicked.connect(self.edit_user)
        toggle.clicked.connect(self.toggle_user)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.user_table = table(["ID", "账号", "姓名", "角色", "状态", "最后登录"])
        self.layout.addWidget(self.user_table)
        self.refresh()

    def refresh(self) -> None:
        self.items = self.gateway.users()
        fill_table(self.user_table, [[u.get("id"), u.get("username"), u.get("real_name"), u.get("role"), u.get("status", 1), u.get("last_login_at") or "-"] for u in self.items])

    def selected_item(self) -> dict[str, Any] | None:
        row = self.user_table.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def add_user(self) -> None:
        dialog = FormDialog("新增用户", [("username", "账号", "username"), ("password", "密码", "123456"), ("real_name", "姓名", "姓名"), ("role", "角色", "admin/teacher/student")], parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.gateway.create_user(dialog.data())
            self.refresh()

    def edit_user(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择用户。")
            return
        dialog = FormDialog("编辑用户", [("real_name", "姓名", ""), ("role", "角色", "admin/teacher/student"), ("status", "状态", "1/0")], item, self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.data()
            data["status"] = int(data.get("status") or 1)
            self.gateway.update_user(int(item["id"]), data)
            self.refresh()

    def toggle_user(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择用户。")
            return
        self.gateway.set_user_status(int(item["id"]), 0 if int(item.get("status") or 1) else 1)
        self.refresh()


class SimpleConfigPage(Page):
    def __init__(self, title: str, loader, headers: list[str], gateway: DataGateway | None = None, config_type: str = "") -> None:
        super().__init__()
        self.loader = loader
        self.headers = headers
        self.gateway = gateway
        self.config_type = config_type
        self.layout.addWidget(make_title(title, "MVP 阶段先展示配置列表，后续补充新增、编辑、测试连接。"))
        action_bar = QFrame()
        action_bar.setObjectName("Toolbar")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(14, 12, 14, 12)
        add = QPushButton("新增配置")
        edit = QPushButton("编辑选中")
        toggle = QPushButton("启用/禁用")
        default = QPushButton("设为默认")
        sync = QPushButton("同步 FastMoss")
        add.clicked.connect(self.add_config)
        edit.clicked.connect(self.edit_config)
        toggle.clicked.connect(self.toggle_config)
        default.clicked.connect(self.set_default)
        sync.clicked.connect(self.sync_fastmoss)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        if config_type == "model":
            actions.addWidget(default)
        if config_type == "third":
            actions.addWidget(sync)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.config_table = table(headers)
        self.layout.addWidget(self.config_table)
        self.refresh()

    def refresh(self) -> None:
        try:
            self.items = self.loader()
        except Exception as exc:
            self.items = []
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        rows = []
        for item in self.items:
            if self.config_type == "model":
                key_text = "已配置" if item.get("has_api_key") or item.get("api_key_encrypted") else "-"
                rows.append([
                    item.get("config_name"),
                    item.get("provider"),
                    item.get("base_url"),
                    item.get("model_name"),
                    key_text,
                    item.get("status"),
                    item.get("is_default"),
                ])
            else:
                rows.append([item.get("config_name"), item.get("service_type"), item.get("status")])
        fill_table(self.config_table, rows)

    def selected_item(self) -> dict[str, Any] | None:
        row = self.config_table.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def model_fields(self) -> list[tuple[str, str, str]]:
        return [
            ("config_name", "配置名称", "豆包选品模型"),
            ("provider", "服务商", "doubao/openai/deepseek/qwen/custom"),
            ("base_url", "Base URL", "https://ark.cn-beijing.volces.com/api/v3"),
            ("api_key_encrypted", "API Key", "火山方舟 API Key"),
            ("model_name", "模型名称", "方舟推理接入点 ID，例如 ep-xxxxxxxx"),
            ("temperature", "温度", "0.7"),
            ("max_tokens", "最大输出", "2000"),
            ("is_default", "默认", "1/0"),
            ("status", "状态", "1/0"),
            ("remark", "备注", ""),
        ]

    def third_fields(self) -> list[tuple[str, str, str]]:
        return [
            ("config_name", "配置名称", "1688 寻源 API"),
            ("service_type", "服务类型", "fastmoss/1688_api/custom_api"),
            ("api_base_url", "API 地址", "https://example.com"),
            ("access_key_encrypted", "Access Key", "API Key 或 Bearer Token"),
            ("secret_key_encrypted", "Secret Key", "可选"),
            (
                "remark",
                "适配 JSON",
                '{"search_path":"/search","method":"POST","items_path":"data.items","total_path":"data.total"}',
            ),
            ("status", "状态", "1/0"),
        ]

    def normalize(self, data: dict[str, str]) -> dict[str, Any]:
        if self.config_type == "model":
            data["temperature"] = float(data.get("temperature") or 0.7)
            data["max_tokens"] = int(data.get("max_tokens") or 2000)
            data["is_default"] = int(data.get("is_default") or 0)
        if self.config_type == "third" and data.get("db_port"):
            data["db_port"] = int(data["db_port"])
        data["status"] = int(data.get("status") or 1)
        return data

    def add_config(self) -> None:
        if not self.gateway:
            return
        dialog = FormDialog("新增配置", self.model_fields() if self.config_type == "model" else self.third_fields(), parent=self)
        if dialog.exec() == QDialog.Accepted:
            try:
                data = self.normalize(dialog.data())
                if self.config_type == "model":
                    saved = self.gateway.save_model_config(data)
                else:
                    saved = self.gateway.save_third_party_config(data)
                self.refresh()
                saved_id = saved.get("id") if isinstance(saved, dict) else None
                if saved_id and not any(int(item.get("id") or 0) == int(saved_id) for item in self.items):
                    QMessageBox.warning(self, "保存异常", "后端返回保存成功，但重新读取数据库时没有找到这条配置。")
                    return
                QMessageBox.information(self, "保存成功", "配置已入库并刷新列表。")
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def edit_config(self) -> None:
        item = self.selected_item()
        if not item or not self.gateway:
            QMessageBox.information(self, "提示", "请先选择配置。")
            return
        dialog = FormDialog("编辑配置", self.model_fields() if self.config_type == "model" else self.third_fields(), item, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                data = self.normalize(dialog.data())
                if self.config_type == "model":
                    self.gateway.save_model_config(data, int(item["id"]))
                else:
                    self.gateway.save_third_party_config(data, int(item["id"]))
                self.refresh()
                QMessageBox.information(self, "保存成功", "配置已更新并刷新列表。")
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def toggle_config(self) -> None:
        item = self.selected_item()
        if not item or not self.gateway:
            QMessageBox.information(self, "提示", "请先选择配置。")
            return
        status = 0 if int(item.get("status") or 1) else 1
        if self.config_type == "model":
            self.gateway.set_model_status(int(item["id"]), status)
        else:
            self.gateway.set_third_party_status(int(item["id"]), status)
        self.refresh()

    def set_default(self) -> None:
        item = self.selected_item()
        if not item or not self.gateway or self.config_type != "model":
            QMessageBox.information(self, "提示", "请先选择模型配置。")
            return
        self.gateway.set_default_model(int(item["id"]))
        self.refresh()

    def sync_fastmoss(self) -> None:
        if not self.gateway or self.config_type != "third":
            return
        try:
            result = self.gateway.sync_fastmoss_products()
            QMessageBox.information(
                self,
                "FastMoss 同步",
                f"{result.get('message', '同步完成')}\n本次入库：{result.get('synced_count', 0)} 条\n当前商品总数：{result.get('total_count', '-')}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "FastMoss 同步失败", str(exc))


class AttributePage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.layout.addWidget(make_title("选品属性", "这些属性既用于展示衍生关系，也用于老师拒绝原因和后期权重计算。"))
        action_bar = QFrame()
        action_bar.setObjectName("Toolbar")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(14, 12, 14, 12)
        add = QPushButton("新增属性")
        edit = QPushButton("编辑选中")
        toggle = QPushButton("启用/禁用")
        add.clicked.connect(self.add_attribute)
        edit.clicked.connect(self.edit_attribute)
        toggle.clicked.connect(self.toggle_attribute)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.attr_table = table(["ID", "属性", "类型", "当前权重"])
        self.layout.addWidget(self.attr_table)
        self.refresh()

    def refresh(self) -> None:
        self.items = self.gateway.attributes()
        fill_table(self.attr_table, [[a.get("id"), a.get("attribute_name"), a.get("attribute_type"), a.get("current_weight")] for a in self.items])

    def selected_item(self) -> dict[str, Any] | None:
        row = self.attr_table.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def fields(self) -> list[tuple[str, str, str]]:
        return [("attribute_name", "属性名称", ""), ("attribute_code", "属性编码", ""), ("attribute_type", "类型", "scene/crowd/risk"), ("description", "说明", ""), ("default_weight", "权重", "1.0"), ("status", "状态", "1/0")]

    def normalize(self, data: dict[str, str]) -> dict[str, Any]:
        data["default_weight"] = float(data.get("default_weight") or 1.0)
        data["status"] = int(data.get("status") or 1)
        return data

    def add_attribute(self) -> None:
        dialog = FormDialog("新增选品属性", self.fields(), parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.gateway.save_attribute(self.normalize(dialog.data()))
            self.refresh()

    def edit_attribute(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择属性。")
            return
        dialog = FormDialog("编辑选品属性", self.fields(), item, self)
        if dialog.exec() == QDialog.Accepted:
            self.gateway.save_attribute(self.normalize(dialog.data()), int(item["id"]))
            self.refresh()

    def toggle_attribute(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择属性。")
            return
        self.gateway.set_attribute_status(int(item["id"]), 0 if int(item.get("status") or 1) else 1)
        self.refresh()


class ThemePage(Page):
    def __init__(self, on_theme_change) -> None:
        super().__init__()
        self.on_theme_change = on_theme_change
        self.layout.addWidget(make_title("主题皮肤", "开发阶段可快速切换软件背景色和主要界面配色。"))

        panel = QFrame()
        panel.setObjectName("Card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        label = QLabel("选择主题")
        label.setObjectName("CardTitle")
        self.theme_select = QComboBox()
        self.theme_select.addItem("深夜蓝", "midnight")
        self.theme_select.addItem("曜石黑", "obsidian")
        self.theme_select.addItem("浅色工作台", "light")
        self.theme_select.setCurrentIndex(2)
        self.theme_select.currentIndexChanged.connect(self.change_theme)
        hint = QLabel("主题只影响界面颜色，不影响登录、商品、教师审核和后端接口。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        panel_layout.addWidget(label)
        panel_layout.addWidget(self.theme_select)
        panel_layout.addWidget(hint)
        self.layout.addWidget(panel)
        self.layout.addStretch()

    def change_theme(self) -> None:
        self.on_theme_change(str(self.theme_select.currentData()))


DEMO_PRODUCT_CARDS = [
    {"title": "无线蓝牙耳机 Pro", "category": "电子产品", "price": 29.99, "sales_count": 12500, "ai_score": 95, "rating": 4.8},
    {"title": "便携式充电宝 20000mAh", "category": "电子产品", "price": 19.99, "sales_count": 8300, "ai_score": 91, "rating": 4.7},
    {"title": "瑜伽垫 加厚防滑", "category": "运动户外", "price": 15.99, "sales_count": 6100, "ai_score": 88, "rating": 4.6},
    {"title": "LED 化妆镜 折叠便携", "category": "美妆个护", "price": 12.99, "sales_count": 9700, "ai_score": 86, "rating": 4.5},
    {"title": "宠物自动喂食器", "category": "宠物用品", "price": 35.99, "sales_count": 4200, "ai_score": 93, "rating": 4.9},
    {"title": "车载手机支架 磁吸", "category": "汽车配件", "price": 9.99, "sales_count": 15800, "ai_score": 82, "rating": 4.4},
    {"title": "儿童益智积木套装", "category": "母婴玩具", "price": 22.99, "sales_count": 7600, "ai_score": 90, "rating": 4.7},
    {"title": "不锈钢保温杯 500ml", "category": "家居日用", "price": 14.99, "sales_count": 11200, "ai_score": 87, "rating": 4.6},
]


DEMO_PRODUCT_CARDS = FASTMOSS_REAL_PRODUCTS


def format_jpy_price(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"￥{amount:,.0f}"


IMAGE_CACHE: dict[tuple[str, int, int], bytes] = {}


class ImageLoadSignals(QObject):
    loaded = Signal(str, int, int, bytes)


class ImageLoadTask(QRunnable):
    def __init__(self, url: str, width: int, height: int, signals: ImageLoadSignals) -> None:
        super().__init__()
        self.url = url
        self.width = width
        self.height = height
        self.signals = signals

    @Slot()
    def run(self) -> None:
        cache_key = (self.url, self.width, self.height)
        if cache_key in IMAGE_CACHE:
            self.signals.loaded.emit(self.url, self.width, self.height, IMAGE_CACHE[cache_key])
            return
        try:
            response = requests.get(
                self.url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 TKSelectionAssistant/1.0"},
            )
            response.raise_for_status()
            image_obj = Image.open(BytesIO(response.content))
            image_obj = ImageOps.exif_transpose(image_obj).convert("RGBA")
            image_obj.thumbnail((self.width, self.height), Image.Resampling.LANCZOS)
            png_buffer = BytesIO()
            image_obj.save(png_buffer, format="PNG", optimize=True)
            content = png_buffer.getvalue()
            IMAGE_CACHE[cache_key] = content
            self.signals.loaded.emit(self.url, self.width, self.height, content)
        except (requests.RequestException, OSError):
            self.signals.loaded.emit(self.url, self.width, self.height, b"")


IMAGE_THREAD_POOL = QThreadPool.globalInstance()
IMAGE_THREAD_POOL.setMaxThreadCount(4)


def pixmap_from_bytes(content: bytes) -> QPixmap:
    pixmap = QPixmap()
    if not content:
        return pixmap
    if pixmap.loadFromData(content):
        return pixmap
    try:
        image_obj = Image.open(BytesIO(content)).convert("RGBA")
        png_buffer = BytesIO()
        image_obj.save(png_buffer, format="PNG")
        pixmap.loadFromData(png_buffer.getvalue(), "PNG")
    except OSError:
        pass
    return pixmap


def create_product_image(url: str, fallback: str, width: int = 206, height: int = 136) -> QFrame:
    image = QFrame()
    image.setObjectName("ProductImage")
    image.setFixedHeight(height)
    image.setMinimumWidth(width)
    image_layout = QVBoxLayout(image)
    image_layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(fallback)
    label.setObjectName("ProductIcon")
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(width, height)
    label.setScaledContents(False)
    image_layout.addWidget(label)

    if not url:
        return image

    def apply_image(loaded_url: str, loaded_width: int, loaded_height: int, content: bytes) -> None:
        if loaded_url != url or loaded_width != width or loaded_height != height:
            return
        pixmap = pixmap_from_bytes(content)
        if not pixmap.isNull():
            label.setText("")
            label.setPixmap(pixmap)

    signals = ImageLoadSignals()
    signals.loaded.connect(apply_image)
    image._image_signals = signals
    IMAGE_THREAD_POOL.start(ImageLoadTask(url, width, height, signals))
    return image


class ProductCard(QFrame):
    def __init__(self, item: dict[str, Any], index: int) -> None:
        super().__init__()
        self.setObjectName("ProductCard")
        self.setMinimumSize(220, 280)
        self.setMaximumWidth(260)

        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        category = str(item.get("category") or "智能推荐")
        price = item.get("price") or item.get("suggested_price_min") or 0
        sales = int(float(item.get("sales_count") or (4200 + index * 850)))
        ai_score = int(float(item.get("ai_score") or item.get("weighted_score") or max(80, 96 - index)))
        rating = float(item.get("rating") or round(4.9 - (index % 5) * 0.1, 1))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(create_product_image(str(item.get("image_url") or ""), "📦", 206, 136))

        name = QLabel(title)
        name.setObjectName("ProductName")
        name.setWordWrap(True)
        layout.addWidget(name)

        tag = QLabel(category)
        tag.setObjectName("CategoryTag")
        layout.addWidget(tag)

        metrics = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("ProductPrice")
        sales_label = QLabel(f"销量 {sales:,} 个")
        sales_label.setObjectName("ProductMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)

        footer = QHBoxLayout()
        rating_label = QLabel(f"★ {rating:.1f}")
        rating_label.setObjectName("RatingText")
        score_label = QLabel(f"AI评分: {ai_score}")
        score_label.setObjectName("AiScore")
        footer.addWidget(rating_label)
        footer.addStretch()
        footer.addWidget(score_label)
        layout.addLayout(footer)


class StudentSelectionPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.setContentsMargins(24, 22, 24, 22)
        self.layout.setSpacing(18)

        self.layout.addWidget(make_title("🤖 AI 智能选品", "根据日本 TK 市场趋势、商品评论和选品属性，生成可审核的衍生品方向。"))

        overview = QHBoxLayout()
        overview.setSpacing(14)
        overview.addWidget(metric_card("今日推荐", "10", "AI 选品候选"))
        overview.addWidget(metric_card("日区热销", "实时", "FastMoss 数据入口"))
        overview.addWidget(metric_card("审核闭环", "可追踪", "属性权重沉淀"))
        self.layout.addLayout(overview)

        chat_box = QFrame()
        chat_box.setObjectName("SelectionHero")
        chat_layout = QVBoxLayout(chat_box)
        chat_layout.setContentsMargins(18, 16, 18, 16)
        chat_layout.setSpacing(12)
        chat_layout.addWidget(QLabel("💬 告诉 AI 你想要什么样的商品"))

        prompt = QLabel("🤖 请告诉我您的选品需求，例如：我想找适合东南亚市场的电子产品，预算在 $10-30 之间，重量轻、利润率高的商品。")
        prompt.setObjectName("PromptHint")
        prompt.setWordWrap(True)
        chat_layout.addWidget(prompt)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入您的选品需求，AI 为您智能推荐...")
        send = QPushButton("🚀 开始选品")
        send.setObjectName("PrimaryAction")
        send.clicked.connect(self.send_chat)
        row.addWidget(self.chat_input, 1)
        row.addWidget(send)
        chat_layout.addLayout(row)

        self.chat_result = QTextEdit()
        self.chat_result.setObjectName("ChatResult")
        self.chat_result.setReadOnly(True)
        self.chat_result.setMaximumHeight(90)
        self.chat_result.setPlaceholderText("AI 选品结果会显示在这里。")
        chat_layout.addWidget(self.chat_result)
        self.layout.addWidget(chat_box)

        heading = QLabel("🌟 AI 推荐商品")
        heading.setObjectName("SectionHeading")
        self.layout.addWidget(heading)

        scroll = QScrollArea()
        scroll.setObjectName("ProductScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("ProductGridWrap")
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(4, 4, 16, 18)
        self.grid.setHorizontalSpacing(34)
        self.grid.setVerticalSpacing(18)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def load_card_items(self) -> list[dict[str, Any]]:
        try:
            items = self.gateway.daily_recommendations()
        except Exception:
            items = []
        if not items or any("�" in str(item.get("title", "")) for item in items[:2]):
            return DEMO_PRODUCT_CARDS
        return (items + DEMO_PRODUCT_CARDS)[:10]

    def send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        answer = self.gateway.ai_chat(text)
        self.chat_result.setPlainText(f"你：{text}\nAI：{answer}")
        self.chat_input.clear()

    def refresh(self) -> None:
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, item in enumerate(self.load_card_items()):
            row = index // 4
            col = index % 4
            self.grid.addWidget(ProductCard(item, index), row, col)
        self.grid.setRowStretch(3, 1)


class TeacherProductCard(QFrame):
    def __init__(self, product: dict[str, Any], on_open) -> None:
        super().__init__()
        self.product = product
        self.on_open = on_open
        self.setObjectName("TeacherProductCard")
        self.setMinimumSize(260, 250)
        self.setMaximumWidth(320)

        title = str(product.get("title") or "未命名原商品")
        category = str(product.get("category") or "未分类")
        price = product.get("price") or 0
        sales = int(float(product.get("sales_count") or 0))
        rank_no = product.get("rank_no") or "-"
        derived_count = product.get("derived_count") or 0
        pending_count = product.get("pending_count") or 0
        comment_count = product.get("comment_count") or 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        rank = QLabel(f"#{rank_no}")
        rank.setObjectName("RankBadge")
        category_label = QLabel(category)
        category_label.setObjectName("CategoryTag")
        top.addWidget(rank)
        top.addStretch()
        top.addWidget(category_label)
        layout.addLayout(top)

        layout.addWidget(create_product_image(str(product.get("image_url") or ""), "📦", 230, 148))

        name = QLabel(title)
        name.setObjectName("ProductName")
        name.setWordWrap(True)
        layout.addWidget(name)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(8)
        metrics.addWidget(self.metric("价格", format_jpy_price(price)), 0, 0)
        metrics.addWidget(self.metric("销量", f"{sales:,} 个"), 0, 1)
        metrics.addWidget(self.metric("衍生品", str(derived_count)), 1, 0)
        metrics.addWidget(self.metric("待审核", str(pending_count)), 1, 1)
        metrics.addWidget(self.metric("评论", str(comment_count)), 2, 0)
        layout.addLayout(metrics)

        open_button = QPushButton("查看衍生品")
        open_button.setObjectName("PrimaryAction")
        open_button.clicked.connect(lambda: self.on_open(self.product))
        layout.addWidget(open_button)

    def metric(self, label: str, value: str) -> QWidget:
        box = QFrame()
        box.setObjectName("MetricBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        label_widget = QLabel(label)
        label_widget.setObjectName("ProductMuted")
        value_widget = QLabel(value)
        value_widget.setObjectName("MetricValue")
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        return box

    def mouseDoubleClickEvent(self, event) -> None:
        self.on_open(self.product)
        super().mouseDoubleClickEvent(event)


class TeacherDashboardPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.setContentsMargins(24, 22, 24, 22)
        self.layout.setSpacing(18)
        self.layout.addWidget(make_title("教师看板", "点击原商品卡片查看 AI 衍生品，并对衍生品方向做通过或拒绝。"))

        stats = QFrame()
        stats.setObjectName("StatsStrip")
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(14)
        self.source_metric = metric_card("原商品", "0", "FastMoss 热销/新品")
        self.derived_metric = metric_card("衍生品", "0", "AI 推荐方向")
        self.pending_metric = metric_card("待审核", "0", "老师未处理")
        stats_layout.addWidget(self.source_metric)
        stats_layout.addWidget(self.derived_metric)
        stats_layout.addWidget(self.pending_metric)
        self.layout.addWidget(stats)

        scroll = QScrollArea()
        scroll.setObjectName("ProductScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("ProductGridWrap")
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(4, 4, 16, 18)
        self.grid.setHorizontalSpacing(28)
        self.grid.setVerticalSpacing(18)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def refresh(self) -> None:
        self.products = self.gateway.hot_products()
        total_derived = sum(int(item.get("derived_count") or 0) for item in self.products)
        total_pending = sum(int(item.get("pending_count") or 0) for item in self.products)
        self.source_metric.findChildren(QLabel)[1].setText(str(len(self.products)))
        self.derived_metric.findChildren(QLabel)[1].setText(str(total_derived))
        self.pending_metric.findChildren(QLabel)[1].setText(str(total_pending))
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, product in enumerate(self.products):
            self.grid.addWidget(TeacherProductCard(product, self.open_product), index // 3, index % 3)
        self.grid.setRowStretch((len(self.products) // 3) + 1, 1)

    def open_product(self, product: dict[str, Any]) -> None:
        dialog = DerivedDialog(self.gateway, product, self)
        dialog.exec()
        self.refresh()


class DerivedDialog(QDialog):
    def __init__(self, gateway: DataGateway, product: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.product = product
        self.setWindowTitle(f"衍生品审核 - {product['title']}")
        self.resize(1100, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(make_title(product["title"], "审核对象是 AI 衍生品，不是具体 1688 商品。"))

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 12, 14, 12)
        generate_button = QPushButton("AI 生成衍生品")
        generate_button.setObjectName("PrimaryAction")
        generate_button.clicked.connect(self.generate_items)
        toolbar_layout.addWidget(generate_button)
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        wrap = QWidget()
        self.cards = QVBoxLayout(wrap)
        scroll.setWidget(wrap)
        layout.addWidget(scroll)

        self.refresh_cards()

    def clear_cards(self) -> None:
        while self.cards.count():
            child = self.cards.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def refresh_cards(self) -> None:
        self.clear_cards()
        items = self.gateway.derived_products(self.product["id"])
        if not items:
            empty = QLabel("暂无衍生品，点击上方按钮由 AI 生成。")
            empty.setObjectName("Muted")
            self.cards.addWidget(empty)
        for item in items:
            self.cards.addWidget(self.card(item))
        self.cards.addStretch()

    def generate_items(self) -> None:
        try:
            result = self.gateway.generate_derived_products(int(self.product["id"]))
            self.refresh_cards()
            mode = "大模型" if result.get("model_used") else "本地规则"
            QMessageBox.information(self, "生成完成", f"已生成 {result.get('count', 0)} 个衍生品方向。\n生成方式：{mode}")
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def card(self, item: dict[str, Any]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        head = QHBoxLayout()
        title = QLabel(f"{item['derived_title']}    分数：{item.get('weighted_score')}    状态：{item.get('review_status')}")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch()
        approve = QPushButton("通过")
        reject = QPushButton("拒绝")
        approve.clicked.connect(lambda: self.approve_item(item))
        reject.clicked.connect(lambda: self.reject_item(item))
        head.addWidget(approve)
        head.addWidget(reject)
        layout.addLayout(head)
        detail = QLabel(
            f"人群：{item.get('target_audience')}\n"
            f"场景：{item.get('usage_scene')}\n"
            f"推荐理由：{item.get('recommendation_reason')}\n"
            f"风险提示：{item.get('risk_notes')}"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        attrs = QHBoxLayout()
        for attr in item.get("attributes", []):
            chip = QLabel(f"{attr.get('attribute_name')} {attr.get('ai_score')}")
            chip.setObjectName("Chip")
            attrs.addWidget(chip)
        attrs.addStretch()
        layout.addLayout(attrs)
        return frame

    def approve_item(self, item: dict[str, Any]) -> None:
        self.gateway.approve(item["id"])
        item["review_status"] = "approved"
        QMessageBox.information(self, "已通过", "衍生品已标记为通过。")
        self.accept()

    def reject_item(self, item: dict[str, Any]) -> None:
        dialog = RejectDialog(self.gateway, item, self)
        if dialog.exec() == QDialog.Accepted:
            QMessageBox.information(self, "已拒绝", "拒绝原因已记录。")
            self.accept()


class RejectDialog(QDialog):
    def __init__(self, gateway: DataGateway, item: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.item = item
        self.setWindowTitle("拒绝原因")
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"拒绝：{item['derived_title']}"))
        self.reason = QComboBox()
        self.attributes = gateway.attributes()
        for attr in self.attributes:
            self.reason.addItem(attr["attribute_name"], attr["id"])
        self.comment = QTextEdit()
        self.comment.setPlaceholderText("可填写补充说明")
        add = QPushButton("+ 新增属性原因")
        add.clicked.connect(self.add_attribute_hint)
        submit = QPushButton("确认拒绝")
        submit.clicked.connect(self.submit)
        layout.addWidget(self.reason)
        layout.addWidget(add)
        layout.addWidget(self.comment)
        layout.addWidget(submit)

    def add_attribute_hint(self) -> None:
        QMessageBox.information(self, "MVP 提示", "新增属性接口已预留。下一阶段会补充弹窗表单并写入 MySQL。")

    def submit(self) -> None:
        attribute_id = int(self.reason.currentData())
        self.gateway.reject(self.item["id"], [attribute_id], self.comment.toPlainText())
        self.item["review_status"] = "rejected"
        self.accept()


THEMES = {
    "midnight": {
        "bg": "#0f1020",
        "sidebar": "#17172a",
        "panel": "#151f3a",
        "panel2": "#162340",
        "hero": "#15213e",
        "input": "#143d68",
        "border": "#2b3d67",
        "text": "#f8fafc",
        "muted": "#8aa4c4",
        "accent": "#ef426b",
        "accent_hover": "#ff5b82",
        "tag": "#3f723f",
        "tag_text": "#7dd3fc",
        "image_a": "#164371",
        "image_b": "#57368b",
        "metric": "#10182f",
    },
    "obsidian": {
        "bg": "#0a0c10",
        "sidebar": "#111318",
        "panel": "#151a21",
        "panel2": "#171f2a",
        "hero": "#171c25",
        "input": "#1d2937",
        "border": "#2f3947",
        "text": "#f3f4f6",
        "muted": "#9ca3af",
        "accent": "#22c55e",
        "accent_hover": "#16a34a",
        "tag": "#1f4c37",
        "tag_text": "#86efac",
        "image_a": "#1f2937",
        "image_b": "#14532d",
        "metric": "#10151c",
    },
    "light": {
        "bg": "#eef3f8",
        "sidebar": "#ffffff",
        "panel": "#ffffff",
        "panel2": "#f8fbff",
        "hero": "#ffffff",
        "input": "#f1f6fc",
        "border": "#d8e2ef",
        "text": "#172033",
        "muted": "#64748b",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "tag": "#dff4e8",
        "tag_text": "#047857",
        "image_a": "#dbeafe",
        "image_b": "#e9d5ff",
        "metric": "#f1f5f9",
    },
}


def apply_style(app: QApplication, theme_name: str = "light") -> None:
    theme = THEMES.get(theme_name, THEMES["light"])
    app.setFont(QFont("Microsoft YaHei UI", 10))
    qss = Template(
        """
        QWidget { background: $bg; color: $text; }
        QLineEdit, QTextEdit, QComboBox {
            background: $input; color: $text; border: 1px solid $border; border-radius: 8px;
            padding: 10px; selection-background-color: $accent;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid $accent;
        }
        QLineEdit::placeholder { color: $muted; }
        QPushButton {
            background: $accent; color: white; border: 0; border-radius: 8px;
            padding: 10px 16px; font-weight: 600;
        }
        QPushButton:hover { background: $accent_hover; }
        QTableWidget {
            background: $panel; alternate-background-color: $panel2; color: $text;
            border: 1px solid $border; border-radius: 8px; gridline-color: $border;
        }
        QTableWidget::item { padding: 8px; border: 0; }
        QTableWidget::item:selected { background: $accent; color: #ffffff; }
        QHeaderView::section {
            background: $panel2; color: $text; padding: 9px; border: 0;
            font-weight: 700;
        }
        QScrollArea { border: 0; }
        QScrollBar:vertical {
            background: transparent; width: 10px; margin: 4px;
        }
        QScrollBar::handle:vertical {
            background: $border; border-radius: 5px; min-height: 32px;
        }
        QScrollBar::handle:vertical:hover { background: $accent; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        #HeroPanel { background: #132238; }
        #HeroTitle { background: transparent; color: #ffffff; font-size: 38px; font-weight: 800; }
        #HeroText { background: transparent; color: #d6e3f6; font-size: 16px; line-height: 1.5; }
        #LoginPanel { background: #ffffff; }
        #LoginTitle { background: transparent; color: #111827; font-size: 30px; font-weight: 800; }
        #Muted { color: $muted; background: transparent; }
        #SidePanel { background: $sidebar; border-right: 1px solid $border; }
        #BrandBox {
            background: $sidebar; border-bottom: 1px solid $border;
        }
        #BrandTitle {
            background: transparent; color: $text; font-size: 20px; font-weight: 900;
        }
        #BrandSub {
            background: transparent; color: $muted; font-size: 11px; letter-spacing: 0px;
        }
        #SideNav {
            background: $sidebar; color: $muted; border: 0; padding: 14px;
            outline: 0;
        }
        #SideNav::item { height: 48px; border-radius: 10px; margin: 5px; padding-left: 14px; }
        #SideNav::item:hover { background: $panel2; color: $text; }
        #SideNav::item:selected { background: $accent; color: #ffffff; }
        #UserBox { background: $panel2; border-top: 1px solid $border; border-radius: 10px; margin: 10px 12px 14px 12px; }
        #UserStatus { background: transparent; color: $text; line-height: 1.4; }
        #SideLoginButton {
            background: $input; color: $text; border-radius: 8px;
            padding: 9px 12px; margin-top: 8px;
        }
        #SideLoginButton:hover { background: $accent_hover; color: #ffffff; }
        #Page { background: $bg; }
        #PageHeader {
            background: $panel; border: 1px solid $border; border-radius: 14px;
        }
        #PageTitle { background: transparent; font-size: 28px; font-weight: 900; color: $text; }
        #Toolbar {
            background: $panel; border: 1px solid $border; border-radius: 12px;
        }
        #StatsStrip {
            background: transparent;
        }
        #MetricCard {
            background: $panel; border: 1px solid $border; border-radius: 14px;
        }
        #DashboardMetric {
            background: transparent; color: $text; font-size: 26px; font-weight: 900;
        }
        #Card {
            background: $panel; border: 1px solid $border; border-radius: 12px;
        }
        #CardTitle { background: transparent; color: $text; font-size: 16px; font-weight: 800; }
        #Chip {
            background: $tag; color: $tag_text; border: 1px solid $border;
            border-radius: 8px; padding: 6px 10px;
        }
        #SelectionHero {
            background: $hero; border: 1px solid $border; border-radius: 16px;
        }
        #PromptHint {
            background: $input; color: $text; border-radius: 8px; padding: 12px;
        }
        #PrimaryAction {
            background: $accent; min-width: 130px;
        }
        #ChatResult {
            background: $metric; border: 1px solid $border; color: $text;
        }
        #SectionHeading {
            background: transparent; color: $text; font-size: 22px; font-weight: 800;
        }
        #ProductScroll {
            background: $bg; border: 0;
        }
        #ProductGridWrap { background: $bg; }
        #ProductCard, #TeacherProductCard {
            background: $panel2; border: 1px solid $border; border-radius: 14px;
        }
        #ProductCard:hover, #TeacherProductCard:hover { border: 1px solid $accent; }
        #ProductImage, #TeacherProductImage {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $image_a, stop:1 $image_b);
            border-radius: 12px;
        }
        #ProductIcon {
            background: transparent; font-size: 38px;
        }
        #ProductName {
            background: transparent; color: $text; font-size: 15px; font-weight: 800;
        }
        #CategoryTag {
            background: $tag; color: $tag_text; border-radius: 5px; padding: 4px 10px;
        }
        #ProductPrice {
            background: transparent; color: $accent; font-size: 20px; font-weight: 800;
        }
        #ProductMuted {
            background: transparent; color: $muted;
        }
        #RatingText {
            background: transparent; color: #facc15; font-weight: 700;
        }
        #AiScore {
            background: transparent; color: #08f3c8; font-weight: 800;
        }
        #RankBadge {
            background: $accent; color: #ffffff; border-radius: 12px; padding: 5px 10px; font-weight: 800;
        }
        #MetricBox {
            background: $metric; border: 1px solid $border; border-radius: 8px;
        }
        #MetricValue {
            background: transparent; color: $text; font-size: 15px; font-weight: 800;
        }
        """
    ).substitute(theme)
    app.setStyleSheet("")
    app.setStyleSheet(qss)
    app.setPalette(app.palette())


def main() -> int:
    app = QApplication(sys.argv)
    apply_style(app)
    gateway = DataGateway()
    window = MainWindow(gateway)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
