from __future__ import annotations

import sys
import json
from io import BytesIO
from pathlib import Path
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PIL import Image, ImageOps
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
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
    QProgressBar,
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


APP_DIR = Path(__file__).resolve().parent
ICON_DIR = APP_DIR / "assets" / "icons"


def icon_path(filename: str) -> str:
    return str(ICON_DIR / filename)



class DataGateway:
    def __init__(self) -> None:
        self.client = ApiClient()
        self.user: dict[str, Any] | None = None
        self.settings = QSettings("YXKJ", "TKCrossBorderAssistant")
        self.restore_session()

    def restore_session(self) -> None:
        token = self.settings.value("auth/token", "", str)
        raw_user = self.settings.value("auth/user", "", str)
        if not raw_user:
            return
        try:
            user = json.loads(raw_user)
        except (TypeError, ValueError):
            self.clear_session()
            return
        if not isinstance(user, dict):
            self.clear_session()
            return
        self.user = user
        if token:
            self.client.token = token
            try:
                self.user = self.client.get("/api/auth/me")
            except ApiError as exc:
                if self.is_invalid_token_error(exc):
                    self.clear_session()
                return

    def save_session(self) -> None:
        self.settings.setValue("auth/user", json.dumps(self.user or {}, ensure_ascii=False))
        self.settings.setValue("auth/token", self.client.token or "")
        self.settings.sync()

    def clear_session(self) -> None:
        self.user = None
        self.client.token = None
        self.settings.remove("auth")
        self.settings.sync()

    def is_invalid_token_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "请重新登录" in str(exc) or "invalid token" in text or "not authenticated" in text or "could not validate credentials" in text

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.client.login(username, password)
        self.user = data["user"]
        self.save_session()
        return self.user

    def hot_products(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/products/hot")

    def daily_recommendations(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/daily-recommendations")

    def derived_products(self, product_id: int) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get(f"/api/teacher/products/{product_id}/derived-products")

    def recommended_derived_products(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.user:
            return []
        products = self.hot_products()
        items: list[dict[str, Any]] = []
        for product in products:
            if len(items) >= limit:
                break
            try:
                derived_items = self.derived_products(int(product["id"]))
            except ApiError:
                derived_items = []
            for derived in derived_items:
                item = dict(derived)
                item["title"] = item.get("derived_title") or item.get("title") or "未命名衍生品"
                item["image_url"] = item.get("supplier_image_url") or item.get("image_url") or product.get("image_url") or ""
                item["price"] = item.get("supplier_price") or item.get("suggested_price_min") or 0
                item["sales_count"] = item.get("supplier_sales_count") or 0
                items.append(item)
                if len(items) >= limit:
                    break
        return items

    def generate_derived_products(self, product_id: int) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "message": "请先登录后端账号"}
        return self.client.post(f"/api/ai/products/{product_id}/generate-derived")

    def attributes(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        if self.user and self.user["role"] == "admin":
            return self.client.get("/api/admin/selection-attributes")
        return self.client.get("/api/selection-attributes")

    def users(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/users")

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/admin/users", payload)

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.put(f"/api/admin/users/{user_id}", payload)

    def set_user_status(self, user_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/users/{user_id}/status", {"status": status})

    def recharge_user_credits(self, user_id: int, credits: int, remark: str = "") -> dict[str, Any]:
        return self.client.post(f"/api/admin/users/{user_id}/credits/recharge", {"credits": credits, "remark": remark})

    def delete_user(self, user_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/users/{user_id}")

    def refresh_me(self) -> dict[str, Any]:
        self.user = self.client.get("/api/auth/me")
        self.save_session()
        return self.user

    def model_configs(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/model-configs")

    def save_model_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        if config_id:
            return self.client.put(f"/api/admin/model-configs/{config_id}", payload)
        return self.client.post("/api/admin/model-configs", payload)

    def set_model_status(self, config_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/model-configs/{config_id}/status", {"status": status})

    def set_default_model(self, config_id: int) -> dict[str, Any]:
        return self.client.post(f"/api/admin/model-configs/{config_id}/default")

    def delete_model_config(self, config_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/model-configs/{config_id}")

    def third_party_configs(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/third-party-configs")

    def save_third_party_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        if config_id:
            return self.client.put(f"/api/admin/third-party-configs/{config_id}", payload)
        return self.client.post("/api/admin/third-party-configs", payload)

    def set_third_party_status(self, config_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/third-party-configs/{config_id}/status", {"status": status})

    def delete_third_party_config(self, config_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/third-party-configs/{config_id}")

    def sync_fastmoss_products(self) -> dict[str, Any]:
        return self.client.post("/api/fastmoss/sync-products?page=1&pagesize=20")

    def auto_publish_candidates(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/auto-publish/candidates")

    def create_auto_publish_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/auto-publish/tasks", payload)

    def create_1688_auto_publish_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/auto-publish/1688/tasks", payload, timeout=60)

    def run_auto_publish_task(self, task_id: str) -> dict[str, Any]:
        return self.client.post(f"/api/auto-publish/tasks/{task_id}/run", timeout=1800)

    def get_auto_publish_task(self, task_id: str) -> dict[str, Any]:
        return self.client.get(f"/api/auto-publish/tasks/{task_id}", timeout=20)

    def latest_auto_publish_result(self) -> dict[str, Any]:
        return self.client.get("/api/auto-publish/latest")

    def ai_chat(self, message: str) -> str:
        return self.client.post("/api/ai/chat-selection", {"message": message})["answer"]

    def pipeline_status(self) -> dict[str, Any]:
        if not self.user:
            return {}
        return self.client.get("/api/pipeline/status")

    def queue_pending_derivations(self, limit: int = 5, min_derived_count: int = 10) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "queued_count": 0, "message": "请先登录后端账号"}
        return self.client.post("/api/pipeline/derivations/queue", {"limit": limit, "min_derived_count": min_derived_count})

    def queue_supplier_matches(self, limit: int = 5, threshold: float = 90, max_candidates: int = 200, page_size: int = 20) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "queued": False, "message": "请先登录后端账号"}
        return self.client.post(
            "/api/pipeline/suppliers/1688/queue",
            {"limit": limit, "threshold": threshold, "max_candidates": max_candidates, "page_size": page_size},
        )

    def start_ai_selection(self, message: str) -> dict[str, Any]:
        return self.client.post("/api/ai/chat-selection", {"message": message})

    def ai_selection_task(self, task_id: int) -> dict[str, Any]:
        return self.client.get(f"/api/ai/selection-tasks/{task_id}")

    def user_search_results(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/ai/search-results")

    def save_attribute(self, payload: dict[str, Any], attribute_id: int | None = None) -> dict[str, Any]:
        if attribute_id:
            return self.client.put(f"/api/admin/selection-attributes/{attribute_id}", payload)
        return self.client.post("/api/admin/selection-attributes", payload)

    def set_attribute_status(self, attribute_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/selection-attributes/{attribute_id}/status", {"status": status})

    def approve(self, derived_id: int) -> None:
        self.client.post(f"/api/teacher/derived-products/{derived_id}/approve")

    def reject(self, derived_id: int, attribute_ids: list[int], comment: str) -> None:
        self.client.post(f"/api/teacher/derived-products/{derived_id}/reject", {"attribute_ids": attribute_ids, "review_comment": comment})

    def search_1688(self, keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.client.post("/api/suppliers/1688/search", {"keyword": keyword, "page": page, "page_size": page_size})

    def search_1688_for_derived(self, derived_id: int, page: int = 1, page_size: int = 20) -> dict[str, Any]:
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


DIMENSION_LABELS = [
    ("dimension_1", "使用场景"),
    ("dimension_2", "商品周期性"),
    ("dimension_3", "目标群体"),
    ("dimension_4", "短视频种草"),
    ("dimension_5", "日本偏好"),
    ("dimension_6", "新奇特"),
    ("dimension_7", "复购属性"),
    ("dimension_8", "竞品属性"),
]


def dimension_items_from_report(item: dict[str, Any]) -> list[tuple[str, str, str]]:
    raw_report = item.get("analysis_report") or {}
    if isinstance(raw_report, str):
        try:
            raw_report = json.loads(raw_report)
        except (TypeError, ValueError):
            raw_report = {}
    result: list[tuple[str, str, str]] = []
    for code, default_name in DIMENSION_LABELS:
        row = raw_report.get(code) if isinstance(raw_report, dict) else None
        if not row and isinstance(raw_report, dict):
            row = raw_report.get(default_name)
        if isinstance(row, dict):
            name = str(row.get("dimension_name") or row.get("维度名称") or default_name)
            level = str(row.get("判定等级") or row.get("rating_level") or row.get("level") or "")
            content = str(row.get("客观分析内容") or row.get("analysis_content") or row.get("content") or "")
            result.append((name, level, content))
        else:
            result.append((default_name, "", ""))
    fallback = {
        "使用场景": item.get("usage_scene") or "",
        "目标群体": item.get("target_audience") or "",
        "短视频种草": item.get("recommendation_reason") or "",
        "竞品属性": item.get("risk_notes") or "",
    }
    return [(name, level, content or str(fallback.get(name, ""))) for name, level, content in result]


def show_analysis_report(parent: QWidget, item: dict[str, Any]) -> None:
    title = str(item.get("title") or item.get("derived_title") or "选品分析报告")
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"选品分析报告 - {title[:40]}")
    dialog.resize(860, 620)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    header = QLabel(title)
    header.setObjectName("PageTitle")
    header.setWordWrap(True)
    layout.addWidget(header)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    grid = QGridLayout(content)
    grid.setContentsMargins(0, 0, 10, 10)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    for index, (name, level, detail) in enumerate(dimension_items_from_report(item)):
        box = QFrame()
        box.setObjectName("MetricBox")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(12, 10, 12, 10)
        box_layout.setSpacing(6)
        name_label = QLabel(name)
        name_label.setObjectName("CardTitle")
        level_label = QLabel(level or "暂无等级")
        level_label.setObjectName("ProductPrice")
        detail_label = QLabel(detail or "暂无分析内容")
        detail_label.setObjectName("ProductMuted")
        detail_label.setWordWrap(True)
        box_layout.addWidget(name_label)
        box_layout.addWidget(level_label)
        box_layout.addWidget(detail_label)
        grid.addWidget(box, index // 2, index % 2)
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)
    close_button = QPushButton("关闭")
    close_button.clicked.connect(dialog.accept)
    actions = QHBoxLayout()
    actions.addStretch()
    actions.addWidget(close_button)
    layout.addLayout(actions)
    dialog.exec()


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
        self.setWindowIcon(QIcon(icon_path("10_TK跨境助手.ico")))
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
        hint = QLabel("请输入服务器账号登录")
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
        self.setWindowIcon(QIcon(icon_path("10_TK跨境助手.ico")))
        self.resize(420, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel("登录账号")
        title.setObjectName("LoginTitle")
        hint = QLabel("请输入服务器账号登录")
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
            user = self.gateway.user
        self.user = user
        self.setWindowTitle("TK 日本跨境智能选品系统")
        self.setWindowIcon(QIcon(icon_path("10_TK跨境助手.ico")))
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
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(QIcon(icon_path("10_TK跨境助手.ico")).pixmap(28, 28))
        brand_icon.setFixedSize(30, 30)
        brand = QLabel("TikTok Japan 跨境选品平台")
        brand.setObjectName("BrandTitle")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand, 1)
        brand_sub = QLabel("AI 选品与审核工作台")
        brand_sub.setObjectName("BrandSub")
        brand_layout.addLayout(brand_row)
        brand_layout.addWidget(brand_sub)

        sidebar.setFixedWidth(230)
        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(230)
        self.nav.setIconSize(QSize(20, 20))
        self.stack = QStackedWidget()

        self.user_avatar = QLabel("未")
        self.user_avatar.setObjectName("UserAvatar")
        self.user_avatar.setAlignment(Qt.AlignCenter)
        self.user_avatar.setFixedSize(34, 34)
        self.user_name = QLabel("未登录")
        self.user_name.setObjectName("UserName")
        self.user_role = QLabel("请登录服务器账号")
        self.user_role.setObjectName("UserRole")
        self.user_status = QLabel("本地界面预览")
        self.user_status.setObjectName("UserStatus")
        self.user_status.setWordWrap(True)
        self.login_button = QPushButton("登录")
        self.login_button.setObjectName("SideLoginButton")
        self.login_button.clicked.connect(self.open_login_dialog)

        user_box = QFrame()
        user_box.setObjectName("UserBox")
        user_layout = QVBoxLayout(user_box)
        user_layout.setContentsMargins(12, 12, 12, 12)
        user_layout.setSpacing(8)
        user_head = QHBoxLayout()
        user_head.setSpacing(9)
        user_text = QVBoxLayout()
        user_text.setSpacing(2)
        user_text.addWidget(self.user_name)
        user_text.addWidget(self.user_role)
        user_head.addWidget(self.user_avatar)
        user_head.addLayout(user_text, 1)
        user_layout.addLayout(user_head)
        user_layout.addWidget(self.user_status)
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
        self.nav.setCurrentRow(2)

    def add_page(self, name: str, page: QWidget, icon: str = "") -> None:
        item = QListWidgetItem(name)
        if icon:
            item.setIcon(QIcon(icon_path(icon)))
        item.setTextAlignment(Qt.AlignVCenter)
        self.nav.addItem(item)
        self.stack.addWidget(page)
        self.pages.append(page)

    def setup_pages(self) -> None:
        self.add_page("智能选品", SelectionStudioPage(self.gateway), "01_智能选品.ico")
        self.add_page("教师看板", TeacherDashboardPage(self.gateway), "02_教师看板.ico")
        self.add_page("任务看板", PipelinePage(self.gateway), "07_第三方API.ico")
        self.add_page("自动上架", AutoPublishPage(self.gateway), "10_TK跨境助手.ico")
        self.add_page("用户管理", AdminUsersPage(self.gateway), "03_用户管理.ico")
        self.add_page("模型配置", SimpleConfigPage("模型配置", self.gateway.model_configs, ["配置名称", "服务商", "类型", "Base URL", "模型", "Key", "状态", "默认"], self.gateway, "model"), "04_模型配置.ico")
        self.add_page("第三方 API", SimpleConfigPage("第三方 API 配置", self.gateway.third_party_configs, ["配置名称", "服务类型", "状态"], self.gateway, "third"), "07_第三方API.ico")
        self.add_page("选品属性", AttributePage(self.gateway), "08_选品属性.ico")
        self.add_page("主题皮肤", ThemePage(self.apply_theme), "05_主题皮肤.ico")

    def update_login_status(self) -> None:
        if self.user:
            api_host = self.gateway.client.base_url.replace("http://", "").replace("https://", "")
            role_map = {"admin": "系统管理员", "teacher": "选品老师", "student": "学生账号"}
            real_name = str(self.user.get("real_name") or self.user.get("username") or "用户")
            role = str(self.user.get("role") or "")
            credits = int(self.user.get("credit_balance") or 0)
            self.user_avatar.setText(real_name[:1].upper())
            self.user_name.setText(real_name)
            self.user_role.setText(role_map.get(role, role or "已登录"))
            self.user_status.setText(f"积分 {credits} · {api_host}")
            self.login_button.setText("切换登录")
            self.setWindowTitle(f"TK 日本跨境智能选品系统 - {self.user.get('real_name')}")
            return
        self.user_avatar.setText("未")
        self.user_name.setText("未登录")
        self.user_role.setText("请登录服务器账号")
        self.user_status.setText("登录后连接后端服务")
        self.login_button.setText("登录")
        self.setWindowTitle("TK 日本跨境智能选品系统")

    def open_login_dialog(self) -> None:
        dialog = LoginDialog(self.gateway, self)
        if dialog.exec() == QDialog.Accepted and dialog.user:
            self.user = dialog.user
            self.update_login_status()
            for page in self.pages:
                if hasattr(page, "loaded"):
                    setattr(page, "loaded", False)
            self.on_page_changed(self.nav.currentRow())

    def on_page_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.pages):
            page = self.pages[index]
            activate = getattr(page, "activate", None)
            if callable(activate):
                try:
                    activate()
                except Exception as exc:
                    if self.gateway.is_invalid_token_error(exc):
                        self.clear_invalid_session()
                        if hasattr(page, "loaded"):
                            setattr(page, "loaded", False)
                        try:
                            activate()
                        except Exception:
                            pass
                        return
                    QMessageBox.warning(self, "加载失败", str(exc))

    def clear_invalid_session(self) -> None:
        self.gateway.clear_session()
        self.user = None
        self.update_login_status()
        self.user_status.setText("请重新登录")

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


class PipelinePage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.addWidget(make_title("任务看板", "正式版业务闭环：FastMoss 入库、AI 衍生、1688 补全、老师审核。"))

        self.metric_wrap = QFrame()
        self.metric_wrap.setObjectName("Panel")
        self.metric_layout = QGridLayout(self.metric_wrap)
        self.metric_layout.setContentsMargins(0, 0, 0, 0)
        self.metric_layout.setHorizontalSpacing(14)
        self.metric_layout.setVerticalSpacing(14)
        self.layout.addWidget(self.metric_wrap)

        actions = QFrame()
        actions.setObjectName("Panel")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(16, 14, 16, 14)
        action_layout.setSpacing(10)
        refresh = QPushButton("刷新状态")
        derive = QPushButton("补齐衍生品")
        match = QPushButton("启动1688补全")
        refresh.clicked.connect(self.refresh)
        derive.clicked.connect(self.queue_derivations)
        match.clicked.connect(self.queue_supplier_matches)
        action_layout.addWidget(refresh)
        action_layout.addWidget(derive)
        action_layout.addWidget(match)
        action_layout.addStretch(1)
        self.layout.addWidget(actions)

        self.detail_table = table(["环节", "状态", "数量", "说明"])
        self.layout.addWidget(self.detail_table, 1)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        status = self.gateway.pipeline_status()
        self.loaded = True
        self.render(status)

    def render(self, status: dict[str, Any]) -> None:
        while self.metric_layout.count():
            item = self.metric_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        fastmoss = status.get("fastmoss") or {}
        families = status.get("families") or {}
        derivation = status.get("derivation") or {}
        supplier = status.get("supplier_1688") or {}
        review = status.get("review") or {}
        cards = [
            metric_card("FastMoss 商品", str(fastmoss.get("product_count") or 0), "当前新品榜入库量"),
            metric_card("商品分族", str(families.get("family_count") or 0), "用于权重学习"),
            metric_card("衍生品", str(derivation.get("derived_count") or 0), "AI 已生成数量"),
            metric_card("待补衍生", str(derivation.get("products_without_enough_derivatives") or 0), "未满10个衍生品的原商品"),
            metric_card("1688 已匹配", str(supplier.get("matched_count") or 0), "已回填真实货源"),
            metric_card("审核记录", str(review.get("review_record_count") or 0), "老师批改沉淀"),
        ]
        for index, card in enumerate(cards):
            self.metric_layout.addWidget(card, index // 3, index % 3)

        latest = fastmoss.get("latest_sync") or {}
        supplier_counts = supplier.get("status_counts") or {}
        review_counts = review.get("status_counts") or {}
        rows = [
            ["FastMoss", latest.get("status") or "未同步", fastmoss.get("product_count") or 0, f"最近日期：{latest.get('request_date') or '-'}"],
            ["标题翻译", "完成", latest.get("translation_success_count") or 0, f"失败：{latest.get('translation_failed_count') or 0}"],
            ["AI 衍生", "可继续", derivation.get("derived_count") or 0, f"待补原商品：{derivation.get('products_without_enough_derivatives') or 0}"],
            ["1688 匹配", "可继续", supplier.get("matched_count") or 0, json.dumps(supplier_counts, ensure_ascii=False)],
            ["老师审核", "进行中", review.get("review_record_count") or 0, json.dumps(review_counts, ensure_ascii=False)],
        ]
        fill_table(self.detail_table, rows)

    def queue_derivations(self) -> None:
        result = self.gateway.queue_pending_derivations(limit=5, min_derived_count=10)
        if not result.get("ok"):
            QMessageBox.information(self, "提示", str(result.get("message") or result))
            return
        QMessageBox.information(self, "任务已提交", f"已加入后台衍生队列：{result.get('queued_count', 0)} 个原商品")
        self.refresh()

    def queue_supplier_matches(self) -> None:
        result = self.gateway.queue_supplier_matches(limit=5, threshold=90, max_candidates=200, page_size=20)
        if not result.get("ok"):
            QMessageBox.information(self, "提示", str(result.get("message") or result))
            return
        QMessageBox.information(self, "任务已提交", "1688 自动补全任务已加入后台队列。" if result.get("queued") else str(result))
        self.refresh()


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
        recharge = QPushButton("充值积分")
        delete_button = QPushButton("删除选中")
        add.clicked.connect(self.add_user)
        edit.clicked.connect(self.edit_user)
        toggle.clicked.connect(self.toggle_user)
        recharge.clicked.connect(self.recharge_user)
        delete_button.clicked.connect(self.delete_user)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addWidget(recharge)
        actions.addWidget(delete_button)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.user_table = table(["ID", "账号", "姓名", "角色", "状态", "积分", "最后登录"])
        self.layout.addWidget(self.user_table)
        self.refresh()

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            self.items = self.gateway.users()
        except Exception as exc:
            self.items = []
            fill_table(self.user_table, [])
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        fill_table(
            self.user_table,
            [
                [
                    u.get("id"),
                    u.get("username"),
                    u.get("real_name"),
                    u.get("role"),
                    u.get("status", 1),
                    u.get("credit_balance", 0),
                    u.get("last_login_at") or "-",
                ]
                for u in self.items
            ],
        )

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

    def recharge_user(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择用户。")
            return
        dialog = FormDialog("充值积分", [("credits", "充值积分", "例如：100"), ("remark", "备注", "手动充值")], parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.data()
        try:
            credits = int(data.get("credits") or 0)
            if credits <= 0:
                raise ValueError("充值积分必须大于0")
            result = self.gateway.recharge_user_credits(int(item["id"]), credits, data.get("remark") or "")
            self.refresh()
            user = result.get("user") if isinstance(result, dict) else {}
            QMessageBox.information(self, "充值成功", f"当前积分：{user.get('credit_balance', '')}")
        except Exception as exc:
            QMessageBox.warning(self, "充值失败", str(exc))

    def delete_user(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择用户。")
            return
        name = str(item.get("username") or item.get("real_name") or item.get("id"))
        confirm = QMessageBox.question(self, "确认删除", f"确定删除用户「{name}」吗？")
        if confirm != QMessageBox.Yes:
            return
        try:
            self.gateway.delete_user(int(item["id"]))
            self.refresh()
            QMessageBox.information(self, "删除成功", "用户已删除。")
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))


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
        delete_button = QPushButton("删除选中")
        default = QPushButton("设为默认")
        sync = QPushButton("同步 FastMoss")
        add.clicked.connect(self.add_config)
        edit.clicked.connect(self.edit_config)
        toggle.clicked.connect(self.toggle_config)
        delete_button.clicked.connect(self.delete_config)
        default.clicked.connect(self.set_default)
        sync.clicked.connect(self.sync_fastmoss)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addWidget(delete_button)
        if config_type == "model":
            actions.addWidget(default)
        if config_type == "third":
            actions.addWidget(sync)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.config_table = table(headers)
        self.layout.addWidget(self.config_table)
        self.refresh()

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            self.items = self.loader()
        except Exception as exc:
            self.items = []
            if self.gateway and self.gateway.is_invalid_token_error(exc):
                self.gateway.clear_session()
                parent = self.window()
                if hasattr(parent, "clear_invalid_session"):
                    parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        rows = []
        for item in self.items:
            if self.config_type == "model":
                key_text = "已配置" if item.get("has_api_key") or item.get("api_key_encrypted") else "-"
                rows.append([
                    item.get("config_name"),
                    item.get("provider"),
                    item.get("model_type") or "general",
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
            ("config_name", "配置名称", "DeepSeek 选品模型"),
            ("provider", "服务商", "doubao/openai/deepseek/qwen/custom"),
            ("model_type", "模型类型", "general/text_translation/product_vision/image_translation/image_generation"),
            ("base_url", "Base URL", "https://api.deepseek.com/v1"),
            ("api_key_encrypted", "API Key", "DeepSeek API Key"),
            ("model_name", "模型名称", "deepseek-chat"),
            ("temperature", "温度", "0.7"),
            ("max_tokens", "最大输出", "12000"),
            ("is_default", "默认", "1/0"),
            ("status", "状态", "1/0"),
            ("remark", "备注", ""),
        ]

    def third_fields(self) -> list[tuple[str, str, str]]:
        return [
            ("config_name", "配置名称", "1688 寻源 API"),
            ("service_type", "服务类型", "fastmoss/1688_api/custom_api/oxylabs/miaoshou/volcengine-mediakit"),
            ("api_base_url", "API 地址", "https://example.com"),
            ("access_key_encrypted", "Access Key", "API Key 或 Bearer Token"),
            ("secret_key_encrypted", "Secret Key", "可选"),
            ("db_host", "数据库地址", ""),
            ("db_port", "端口", "3306"),
            ("db_name", "数据库名", ""),
            ("db_user", "用户名", ""),
            ("db_password_encrypted", "数据库密码", ""),
            ("db_query_template", "请求模板/SQL", ""),
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

    def delete_config(self) -> None:
        item = self.selected_item()
        if not item or not self.gateway:
            QMessageBox.information(self, "提示", "请先选择配置。")
            return
        name = str(item.get("config_name") or item.get("id"))
        confirm = QMessageBox.question(self, "确认删除", f"确定删除配置「{name}」吗？")
        if confirm != QMessageBox.Yes:
            return
        try:
            if self.config_type == "model":
                self.gateway.delete_model_config(int(item["id"]))
            else:
                self.gateway.delete_third_party_config(int(item["id"]))
            self.refresh()
            QMessageBox.information(self, "删除成功", "配置已删除。")
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))

    def set_default(self) -> None:
        item = self.selected_item()
        if not item or not self.gateway or self.config_type != "model":
            QMessageBox.information(self, "提示", "请先选择模型配置。")
            return
        try:
            self.gateway.set_default_model(int(item["id"]))
            self.refresh()
            QMessageBox.information(self, "设置成功", "默认模型已更新。")
        except Exception as exc:
            QMessageBox.warning(self, "设置失败", str(exc))

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


def format_jpy_price(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,.0f}円"


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
            try:
                image_obj = Image.open(BytesIO(response.content))
                image_obj = ImageOps.exif_transpose(image_obj).convert("RGBA")
                image_obj = ImageOps.fit(
                    image_obj,
                    (self.width, self.height),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                png_buffer = BytesIO()
                image_obj.save(png_buffer, format="PNG", optimize=True)
                content = png_buffer.getvalue()
            except OSError:
                content = response.content
            IMAGE_CACHE[cache_key] = content
            self.signals.loaded.emit(self.url, self.width, self.height, content)
        except requests.RequestException:
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
    image.setFixedSize(width, height)
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
        try:
            if not pixmap.isNull():
                label.setText("")
                label.setPixmap(pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif url:
                label.setText("图片加载失败")
        except RuntimeError:
            return

    signals = ImageLoadSignals()
    signals.loaded.connect(apply_image)
    image._image_signals = signals
    IMAGE_THREAD_POOL.start(ImageLoadTask(url, width, height, signals))
    return image


class ProductCard(QFrame):
    def __init__(self, item: dict[str, Any], index: int) -> None:
        super().__init__()
        self.setObjectName("ProductCard")
        self.setMinimumSize(250, 370)
        self.setMaximumWidth(270)

        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        sales = int(float(item.get("supplier_sales_count") or item.get("sales_count") or 0))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 230, 230))

        name = QLabel(title)
        name.setObjectName("ProductName")
        name.setWordWrap(True)
        name.setToolTip(title)
        name.setText(title[:14])
        layout.addWidget(name)

        metrics = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("ProductPrice")
        sales_label = QLabel(f"销量 {sales:,} 个")
        sales_label.setObjectName("ProductMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)


class CompactProductCard(QFrame):
    def __init__(self, item: dict[str, Any], index: int, on_click=None) -> None:
        super().__init__()
        self.item = item
        self.on_click = on_click
        self.setObjectName("CompactProductCard")
        self.setFixedSize(148, 242)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击查看选品分析报告")

        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        sales = int(float(item.get("supplier_sales_count") or item.get("sales_count") or 0))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 132, 132))

        name = QLabel(title[:14])
        name.setObjectName("CompactProductName")
        name.setToolTip(title)
        name.setWordWrap(True)
        layout.addWidget(name)

        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("CompactProductPrice")
        layout.addWidget(price_label)

        sales_label = QLabel(f"销量 {sales:,} 个")
        sales_label.setObjectName("CompactProductMuted")
        layout.addWidget(sales_label)

    def mousePressEvent(self, event) -> None:
        if self.on_click:
            self.on_click(self.item)
        super().mousePressEvent(event)


class StudentSelectionPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.setContentsMargins(24, 16, 24, 18)
        self.layout.setSpacing(10)

        chat_box = QFrame()
        chat_box.setObjectName("SelectionHero")
        chat_layout = QVBoxLayout(chat_box)
        chat_layout.setContentsMargins(18, 16, 18, 16)
        chat_layout.setSpacing(12)
        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("我想找适合东南亚市场的电子产品，预算在 $10-30 之间，重量轻、利润率高的商品。")
        self.selection_task_id: int | None = None
        self.selection_timer = QTimer(self)
        self.selection_timer.setInterval(2500)
        self.selection_timer.timeout.connect(self.poll_selection_task)
        self.send_button = QPushButton("🚀 开始选品")
        self.send_button.setObjectName("PrimaryAction")
        self.send_button.clicked.connect(self.send_chat)
        row.addWidget(self.chat_input, 1)
        row.addWidget(self.send_button)
        chat_layout.addLayout(row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("Muted")
        self.progress_label.hide()
        chat_layout.addWidget(self.progress_bar)
        chat_layout.addWidget(self.progress_label)

        self.layout.addWidget(chat_box)

        search_heading = QLabel("本次搜索结果")
        search_heading.setObjectName("SectionHeading")
        self.layout.addWidget(search_heading)

        search_scroll = QScrollArea()
        search_scroll.setObjectName("ProductScroll")
        search_scroll.setWidgetResizable(True)
        search_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        search_scroll.setMinimumHeight(420)
        search_scroll.setMaximumHeight(450)
        search_content = QWidget()
        search_content.setObjectName("ProductGridWrap")
        self.search_result_grid = QGridLayout(search_content)
        self.search_result_grid.setContentsMargins(4, 4, 16, 18)
        self.search_result_grid.setHorizontalSpacing(14)
        self.search_result_grid.setVerticalSpacing(16)
        search_scroll.setWidget(search_content)
        self.search_result_content = search_content
        self.layout.addWidget(search_scroll)

        heading_bar = QWidget()
        heading_layout = QHBoxLayout(heading_bar)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("🌟 衍生品推荐")
        heading.setObjectName("SectionHeading")
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("IconButton")
        refresh_button.setFixedSize(54, 30)
        refresh_button.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh_button.setIconSize(QSize(16, 16))
        refresh_button.setToolTip("刷新商品数据")
        refresh_button.clicked.connect(self.force_refresh)
        self.refresh_button = refresh_button
        heading_layout.addWidget(heading)
        heading_layout.addWidget(refresh_button)
        heading_layout.addStretch()
        self.layout.addWidget(heading_bar)

        carousel = QFrame()
        carousel.setObjectName("ProductCarousel")
        carousel.setFixedHeight(258)
        carousel_layout = QHBoxLayout(carousel)
        carousel_layout.setContentsMargins(0, 0, 0, 0)
        carousel_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("ProductScroll")
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(258)
        content = QWidget()
        content.setObjectName("ProductGridWrap")
        self.product_row = QHBoxLayout(content)
        self.product_row.setContentsMargins(4, 4, 4, 12)
        self.product_row.setSpacing(10)
        scroll.setWidget(content)
        self.product_scroll = scroll
        self.product_content = content
        carousel_layout.addWidget(scroll, 1)
        self.layout.addWidget(carousel)

        new_heading = QLabel("新品榜单")
        new_heading.setObjectName("SectionHeading")
        self.layout.addWidget(new_heading)

        new_scroll = QScrollArea()
        new_scroll.setObjectName("ProductScroll")
        new_scroll.setWidgetResizable(True)
        new_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        new_content = QWidget()
        new_content.setObjectName("ProductGridWrap")
        self.new_product_grid = QGridLayout(new_content)
        self.new_product_grid.setContentsMargins(4, 4, 16, 18)
        self.new_product_grid.setHorizontalSpacing(14)
        self.new_product_grid.setVerticalSpacing(16)
        new_scroll.setWidget(new_content)
        self.new_product_content = new_content
        self.layout.addWidget(new_scroll, 1)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def force_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        try:
            self.refresh()
            self.loaded = True
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "刷新失败", str(exc))
        finally:
            self.refresh_button.setEnabled(True)

    def load_card_items(self) -> list[dict[str, Any]]:
        items = self.gateway.recommended_derived_products(10)
        return items[:10]

    def load_new_items(self) -> list[dict[str, Any]]:
        return self.gateway.daily_recommendations()

    def load_search_items(self) -> list[dict[str, Any]]:
        return self.gateway.user_search_results()

    def send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        try:
            result = self.gateway.start_ai_selection(text)
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "启动失败", str(exc))
            return
        self.selection_task_id = int(result.get("task_id") or 0)
        if not self.selection_task_id:
            QMessageBox.warning(self, "启动失败", "后端没有返回任务ID")
            return
        if "credit_balance" in result and self.gateway.user is not None:
            self.gateway.user["credit_balance"] = result.get("credit_balance")
            parent = self.window()
            if hasattr(parent, "user"):
                parent.user = self.gateway.user
            if hasattr(parent, "update_login_status"):
                parent.update_login_status()
        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText(str(result.get("message") or "AI 智能选品任务已开始"))
        self.progress_label.show()
        self.selection_timer.start()
        self.poll_selection_task()

    def poll_selection_task(self) -> None:
        if not self.selection_task_id:
            return
        try:
            status = self.gateway.ai_selection_task(self.selection_task_id)
        except Exception as exc:
            self.selection_timer.stop()
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            QMessageBox.warning(self, "任务查询失败", str(exc))
            return
        progress = int(status.get("progress") or 0)
        message = str(status.get("message") or status.get("stage") or "正在选品")
        self.progress_bar.setValue(max(0, min(100, progress)))
        self.progress_label.setText(message)
        if status.get("status") == "success":
            self.selection_timer.stop()
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"选品完成，生成 {status.get('success_count') or 0} 个商品")
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.chat_input.clear()
            self.refresh()
        elif status.get("status") == "failed":
            self.selection_timer.stop()
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.progress_label.setText("选品失败")
            QMessageBox.warning(self, "选品失败", str(status.get("error_message") or "任务执行失败"))

    def refresh(self) -> None:
        while self.product_row.count():
            child = self.product_row.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        while self.new_product_grid.count():
            child = self.new_product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        while self.search_result_grid.count():
            child = self.search_result_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        search_items = self.load_search_items()
        derived_items = self.load_card_items()
        new_items = self.load_new_items()
        columns = 6
        self.search_result_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        if not search_items:
            empty_search = QLabel("暂无搜索结果，输入需求后点击开始选品。")
            empty_search.setObjectName("Muted")
            self.search_result_grid.addWidget(empty_search, 0, 0)
            self.search_result_content.setMinimumHeight(64)
        else:
            for index, item in enumerate(search_items):
                card = ProductCard(item, index)
                card.setCursor(Qt.PointingHandCursor)
                card.setToolTip("点击查看选品分析报告")
                card.mousePressEvent = lambda event, current=item: show_analysis_report(self, current)
                self.search_result_grid.addWidget(card, index // columns, index % columns)
            self.search_result_grid.setColumnStretch(columns, 1)
            search_rows = max(1, (len(search_items) + columns - 1) // columns)
            self.search_result_content.setMinimumHeight(search_rows * 386 + 24)
        if not derived_items:
            empty = QLabel("暂无衍生品，先在任务看板补齐衍生品。")
            empty.setObjectName("Muted")
            self.product_row.addWidget(empty)
        else:
            for index, item in enumerate(derived_items):
                self.product_row.addWidget(CompactProductCard(item, index, self.show_derived_report))
        self.product_row.addStretch()
        content_width = max(1, len(derived_items)) * 148 + max(0, len(derived_items) - 1) * 10 + 8
        self.product_content.setFixedWidth(content_width)
        self.product_content.setFixedHeight(252)
        self.new_product_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        for index, item in enumerate(new_items):
            self.new_product_grid.addWidget(ProductCard(item, index), index // columns, index % columns)
        self.new_product_grid.setColumnStretch(columns, 1)
        rows = max(1, (len(new_items) + columns - 1) // columns)
        self.new_product_content.setMinimumHeight(rows * 386 + 24)

    def show_derived_report(self, item: dict[str, Any]) -> None:
        show_analysis_report(self, item)

    def scroll_products_next(self) -> None:
        self.product_content.adjustSize()
        QApplication.processEvents()
        bar = self.product_scroll.horizontalScrollBar()
        maximum = bar.maximum()
        if maximum <= 0:
            self.product_content.setFixedWidth(self.product_scroll.viewport().width() + 292)
            QApplication.processEvents()
            maximum = bar.maximum()
        step = max(292, self.product_scroll.viewport().width() - 120)
        next_value = bar.value() + step
        if next_value >= maximum:
            next_value = 0
        bar.setValue(next_value)


class StudioNewProductCard(QFrame):
    def __init__(self, item: dict[str, Any], index: int, on_click=None) -> None:
        super().__init__()
        self.item = item
        self.on_click = on_click
        self.setObjectName("StudioNewCard")
        self.setFixedSize(190, 286)
        self.setCursor(Qt.PointingHandCursor)
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        sales = int(float(item.get("supplier_sales_count") or item.get("sales_count") or 0))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 172, 132))
        name = QLabel(title[:14])
        name.setObjectName("StudioNewName")
        name.setWordWrap(True)
        name.setToolTip(title)
        layout.addWidget(name)
        tag = QLabel("新品")
        tag.setObjectName("StudioNewTag")
        tag.setFixedWidth(42)
        layout.addWidget(tag)
        metrics = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("StudioNewPrice")
        sales_label = QLabel(f"销量 {sales:,}")
        sales_label.setObjectName("StudioNewMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)

    def mousePressEvent(self, event) -> None:
        if self.on_click:
            self.on_click(self.item)
        super().mousePressEvent(event)


class StudioCompactCard(QFrame):
    def __init__(self, item: dict[str, Any], on_click=None) -> None:
        super().__init__()
        self.item = item
        self.on_click = on_click
        self.setObjectName("StudioCompactCard")
        self.setFixedSize(132, 188)
        self.setCursor(Qt.PointingHandCursor)
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        sales = int(float(item.get("supplier_sales_count") or item.get("sales_count") or 0))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 118, 105))
        name = QLabel(title[:12])
        name.setObjectName("StudioCompactName")
        name.setWordWrap(True)
        name.setToolTip(title)
        layout.addWidget(name)
        footer = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("StudioCompactPrice")
        sales_label = QLabel(f"{sales:,}")
        sales_label.setObjectName("StudioCompactMuted")
        footer.addWidget(price_label)
        footer.addStretch()
        footer.addWidget(sales_label)
        layout.addLayout(footer)

    def mousePressEvent(self, event) -> None:
        if self.on_click:
            self.on_click(self.item)
        super().mousePressEvent(event)


class SelectionStudioPage(Page):
    """智能选品首屏：AI 对话 + 新品榜单。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.selection_task_id: int | None = None
        self.selection_timer = QTimer(self)
        self.selection_timer.setInterval(2500)
        self.selection_timer.timeout.connect(self.poll_selection_task)
        self.layout.setContentsMargins(28, 22, 28, 22)
        self.layout.setSpacing(14)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("AI智能选品")
        title.setObjectName("StudioTitle")
        subtitle = QLabel("与AI对话，发现 TikTok Japan 热销商品")
        subtitle.setObjectName("Muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch()
        tutorial = QPushButton("◉  使用教程")
        tutorial.setObjectName("StudioTutorial")
        tutorial.clicked.connect(self.show_tutorial)
        heading.addWidget(tutorial)
        self.layout.addLayout(heading)

        chat = QFrame()
        chat.setObjectName("StudioChat")
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(18, 15, 18, 15)
        chat_layout.setSpacing(9)
        chat_header = QHBoxLayout()
        dot = QLabel("●")
        dot.setObjectName("StudioDot")
        assistant_label = QLabel("AI 选品助手")
        assistant_label.setObjectName("StudioPanelTitle")
        market_label = QLabel("日本站 · 实时分析")
        market_label.setObjectName("StudioMarket")
        chat_header.addWidget(dot)
        chat_header.addWidget(assistant_label)
        chat_header.addStretch()
        chat_header.addWidget(market_label)
        chat_layout.addLayout(chat_header)
        self.chat_history = QVBoxLayout()
        self.chat_history.setSpacing(7)
        self.chat_history.addWidget(self._bubble("你好，我可以根据你的需求推荐适合 TikTok Japan 的商品。", False))
        chat_layout.addLayout(self.chat_history)
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("帮我找适合日本学生、轻小件、1000円以内的桌面收纳商品")
        self.chat_input.returnPressed.connect(self.send_chat)
        self.send_button = QPushButton("开始选品")
        self.send_button.setObjectName("StudioPrimary")
        self.send_button.clicked.connect(self.send_chat)
        prompt_row.addWidget(self.chat_input, 1)
        prompt_row.addWidget(self.send_button)
        chat_layout.addLayout(prompt_row)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in ("日本小众家居好物", "学生党平价好物", "轻小件高利润"):
            chip = QPushButton(text)
            chip.setObjectName("StudioChip")
            chip.clicked.connect(lambda checked=False, value=text: self.chat_input.setText(value))
            chips.addWidget(chip)
        chips.addStretch()
        chat_layout.addLayout(chips)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.progress_label = QLabel()
        self.progress_label.setObjectName("Muted")
        self.progress_label.hide()
        chat_layout.addWidget(self.progress_bar)
        chat_layout.addWidget(self.progress_label)
        self.layout.addWidget(chat)

        new_header = QHBoxLayout()
        new_title = QLabel("新品榜单")
        new_title.setObjectName("StudioSectionTitle")
        new_meta = QLabel("FastMoss · 日本站最新商品")
        new_meta.setObjectName("StudioMarket")
        new_header.addWidget(new_title)
        new_header.addSpacing(8)
        new_header.addWidget(new_meta)
        new_header.addStretch()
        refresh = QPushButton()
        refresh.setObjectName("StudioIconButton")
        refresh.setFixedSize(34, 34)
        refresh.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh.setIconSize(QSize(17, 17))
        refresh.setToolTip("刷新新品榜单")
        refresh.clicked.connect(self.force_refresh)
        new_header.addWidget(refresh)
        self.layout.addLayout(new_header)

        scroll = QScrollArea()
        scroll.setObjectName("StudioScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("StudioGrid")
        self.new_product_grid = QGridLayout(content)
        self.new_product_grid.setContentsMargins(4, 4, 4, 18)
        self.new_product_grid.setHorizontalSpacing(12)
        self.new_product_grid.setVerticalSpacing(12)
        self.new_product_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)

    @staticmethod
    def _bubble(text: str, user: bool) -> QFrame:
        bubble = QFrame()
        bubble.setObjectName("StudioBubbleUser" if user else "StudioBubbleAi")
        bubble_layout = QHBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("StudioBubbleText")
        bubble_layout.addWidget(label)
        bubble_layout.setAlignment(Qt.AlignRight if user else Qt.AlignLeft)
        return bubble

    def show_tutorial(self) -> None:
        QMessageBox.information(
            self,
            "使用教程",
            "1. 描述你想找的商品、人群、预算或使用场景。\n"
            "2. 点击“开始选品”，AI 会生成本次推荐结果。\n"
            "3. 下方新品榜单展示日本站最新商品。\n"
            "4. 商品图片和销量以后台最新数据为准。",
        )

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def force_refresh(self) -> None:
        try:
            self.refresh()
            self.loaded = True
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "刷新失败", str(exc))

    def send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_history.addWidget(self._bubble(text, True))
        try:
            result = self.gateway.start_ai_selection(text)
        except Exception as exc:
            QMessageBox.warning(self, "启动失败", str(exc))
            return
        self.selection_task_id = int(result.get("task_id") or 0)
        if "credit_balance" in result and self.gateway.user is not None:
            self.gateway.user["credit_balance"] = result.get("credit_balance")
            parent = self.window()
            if hasattr(parent, "user"):
                parent.user = self.gateway.user
            if hasattr(parent, "update_login_status"):
                parent.update_login_status()
        self.chat_history.addWidget(self._bubble("好的，我正在根据你的需求分析日本市场商品，请稍候。", False))
        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText(str(result.get("message") or "AI 智能选品任务已开始"))
        self.progress_label.show()
        self.selection_timer.start()
        self.poll_selection_task()

    def poll_selection_task(self) -> None:
        if not self.selection_task_id:
            return
        try:
            status = self.gateway.ai_selection_task(self.selection_task_id)
        except Exception as exc:
            self.selection_timer.stop()
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            QMessageBox.warning(self, "任务查询失败", str(exc))
            return
        self.progress_bar.setValue(max(0, min(100, int(status.get("progress") or 0))))
        self.progress_label.setText(str(status.get("message") or status.get("stage") or "正在选品"))
        if status.get("status") == "success":
            self.selection_timer.stop()
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"选品完成，生成 {status.get('success_count') or 0} 个商品")
            self.chat_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.chat_history.addWidget(self._bubble("已完成本次选品，推荐结果已保存到你的账号。", False))
        elif status.get("status") == "failed":
            self.selection_timer.stop()
            self.chat_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.progress_label.setText("选品失败，积分已按后端结果处理")

    def refresh(self) -> None:
        items = self.gateway.daily_recommendations()
        while self.new_product_grid.count():
            child = self.new_product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, item in enumerate(items):
            self.new_product_grid.addWidget(StudioNewProductCard(item, index), index // 6, index % 6)
        self.new_product_grid.setColumnStretch(6, 1)


class StudioSelectionPage(Page):
    """方案三：将搜索、推荐和分析报告放在同一工作台内。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.selection_task_id: int | None = None
        self.selection_timer = QTimer(self)
        self.selection_timer.setInterval(2500)
        self.selection_timer.timeout.connect(self.poll_selection_task)
        self.layout.setContentsMargins(24, 18, 24, 18)
        self.layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("StudioHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("AI智能选品")
        title.setObjectName("StudioTitle")
        subtitle = QLabel("与 AI 对话，发现 TikTok Japan 热销商品")
        subtitle.setObjectName("Muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        refresh = QPushButton()
        refresh.setObjectName("StudioIconButton")
        refresh.setFixedSize(38, 38)
        refresh.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh.setIconSize(QSize(18, 18))
        refresh.setToolTip("刷新选品数据")
        refresh.clicked.connect(self.force_refresh)
        header_layout.addWidget(refresh)
        self.layout.addWidget(header)

        workspace = QHBoxLayout()
        workspace.setSpacing(14)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        chat = QFrame()
        chat.setObjectName("StudioChat")
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(16, 14, 16, 14)
        chat_layout.setSpacing(10)
        chat_head = QHBoxLayout()
        assistant_dot = QLabel("●")
        assistant_dot.setObjectName("StudioDot")
        chat_label = QLabel("AI 选品助手")
        chat_label.setObjectName("StudioPanelTitle")
        chat_head.addWidget(assistant_dot)
        chat_head.addWidget(chat_label)
        chat_head.addStretch()
        chat_head.addWidget(QLabel("日本站 · 实时分析"))
        chat_layout.addLayout(chat_head)
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("帮我找适合日本学生、轻小件、1000円以内的桌面收纳商品")
        self.chat_input.returnPressed.connect(self.send_chat)
        self.send_button = QPushButton("开始选品")
        self.send_button.setObjectName("StudioPrimary")
        self.send_button.clicked.connect(self.send_chat)
        prompt_row.addWidget(self.chat_input, 1)
        prompt_row.addWidget(self.send_button)
        chat_layout.addLayout(prompt_row)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in ("日本小众家居好物", "学生党平价好物", "轻小件高利润"):
            chip = QPushButton(text)
            chip.setObjectName("StudioChip")
            chip.clicked.connect(lambda checked=False, value=text: self.chat_input.setText(value))
            chips.addWidget(chip)
        chips.addStretch()
        chat_layout.addLayout(chips)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.progress_label = QLabel()
        self.progress_label.setObjectName("Muted")
        self.progress_label.hide()
        chat_layout.addWidget(self.progress_bar)
        chat_layout.addWidget(self.progress_label)
        left_layout.addWidget(chat)

        self.search_result_scroll, self.search_result_content, self.search_result_row = self._carousel("本次搜索结果", "暂无搜索结果，输入需求后开始选品。")
        left_layout.addWidget(self.search_result_scroll)
        self.derived_scroll, self.derived_content, self.derived_row = self._carousel("衍生品推荐", "暂无衍生品，先在任务看板补齐衍生品。")
        left_layout.addWidget(self.derived_scroll)

        new_title = QLabel("新品榜单")
        new_title.setObjectName("StudioSectionTitle")
        left_layout.addWidget(new_title)
        new_scroll = QScrollArea()
        new_scroll.setObjectName("StudioScroll")
        new_scroll.setWidgetResizable(True)
        new_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        new_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        new_content = QWidget()
        new_content.setObjectName("StudioGrid")
        self.new_product_grid = QGridLayout(new_content)
        self.new_product_grid.setContentsMargins(4, 4, 4, 18)
        self.new_product_grid.setHorizontalSpacing(12)
        self.new_product_grid.setVerticalSpacing(12)
        new_scroll.setWidget(new_content)
        left_layout.addWidget(new_scroll, 1)
        workspace.addWidget(left, 1)

        self.report_panel = QFrame()
        self.report_panel.setObjectName("StudioReport")
        self.report_panel.setFixedWidth(314)
        report_layout = QVBoxLayout(self.report_panel)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_layout.setSpacing(10)
        report_title = QLabel("选品分析报告")
        report_title.setObjectName("StudioPanelTitle")
        report_layout.addWidget(report_title)
        report_tabs = QHBoxLayout()
        report_tabs.setSpacing(4)
        self.report_tab_buttons: list[QPushButton] = []
        for tab_name in ("选品分析报告", "人群匹配", "使用场景"):
            tab = QPushButton(tab_name)
            tab.setObjectName("StudioReportTab")
            tab.setCheckable(True)
            tab.setChecked(tab_name == "选品分析报告")
            tab.clicked.connect(lambda checked=False, name=tab_name, button=tab: self._select_report_tab(name, button))
            self.report_tab_buttons.append(tab)
            report_tabs.addWidget(tab)
        report_layout.addLayout(report_tabs)
        self.report_product = QLabel("选择商品查看分析")
        self.report_product.setObjectName("StudioReportTitle")
        self.report_product.setWordWrap(True)
        report_layout.addWidget(self.report_product)
        self.report_image_box = QWidget()
        self.report_image_layout = QVBoxLayout(self.report_image_box)
        self.report_image_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.addWidget(self.report_image_box)
        self.report_summary = QLabel("选择商品后显示销量和综合参考")
        self.report_summary.setObjectName("StudioSummaryText")
        self.report_summary.setWordWrap(True)
        report_layout.addWidget(self.report_summary)
        self.report_dimensions = QVBoxLayout()
        self.report_dimensions.setSpacing(6)
        report_layout.addLayout(self.report_dimensions)
        report_layout.addStretch()
        report_hint = QLabel("点击商品卡片查看完整维度报告")
        report_hint.setObjectName("Muted")
        report_hint.setWordWrap(True)
        report_layout.addWidget(report_hint)
        workspace.addWidget(self.report_panel)
        self.layout.addLayout(workspace, 1)
        self.report_item: dict[str, Any] | None = None
        self.report_tab = "选品分析报告"
        self._show_report(None)

    def _carousel(self, title: str, empty_text: str):
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("StudioSectionTitle")
        wrapper_layout.addWidget(heading)
        scroll = QScrollArea()
        scroll.setObjectName("StudioScroll")
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(232)
        content = QWidget()
        content.setObjectName("StudioCarousel")
        row = QHBoxLayout(content)
        row.setContentsMargins(4, 4, 4, 8)
        row.setSpacing(10)
        empty = QLabel(empty_text)
        empty.setObjectName("Muted")
        row.addWidget(empty)
        scroll.setWidget(content)
        carousel_bar = QHBoxLayout()
        carousel_bar.setContentsMargins(0, 0, 0, 0)
        carousel_bar.setSpacing(4)
        carousel_bar.addWidget(scroll, 1)
        previous = QPushButton("‹")
        previous.setObjectName("StudioCarouselArrow")
        previous.setFixedSize(28, 54)
        previous.setToolTip("向左查看")
        previous.clicked.connect(lambda: scroll.horizontalScrollBar().setValue(max(0, scroll.horizontalScrollBar().value() - 260)))
        following = QPushButton("›")
        following.setObjectName("StudioCarouselArrow")
        following.setFixedSize(28, 54)
        following.setToolTip("向右查看")
        following.clicked.connect(lambda: self._scroll_carousel(scroll, 260))
        carousel_bar.insertWidget(0, previous)
        carousel_bar.addWidget(following)
        wrapper_layout.addLayout(carousel_bar)
        return wrapper, content, row

    @staticmethod
    def _scroll_carousel(scroll: QScrollArea, step: int) -> None:
        bar = scroll.horizontalScrollBar()
        value = bar.value() + step
        bar.setValue(0 if value >= bar.maximum() else value)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def force_refresh(self) -> None:
        try:
            self.refresh()
            self.loaded = True
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "刷新失败", str(exc))

    def send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        try:
            result = self.gateway.start_ai_selection(text)
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "启动失败", str(exc))
            return
        self.selection_task_id = int(result.get("task_id") or 0)
        if "credit_balance" in result and self.gateway.user is not None:
            self.gateway.user["credit_balance"] = result.get("credit_balance")
            parent = self.window()
            if hasattr(parent, "user"):
                parent.user = self.gateway.user
            if hasattr(parent, "update_login_status"):
                parent.update_login_status()
        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText(str(result.get("message") or "AI 智能选品任务已开始"))
        self.progress_label.show()
        self.selection_timer.start()
        self.poll_selection_task()

    def poll_selection_task(self) -> None:
        if not self.selection_task_id:
            return
        try:
            status = self.gateway.ai_selection_task(self.selection_task_id)
        except Exception as exc:
            self.selection_timer.stop()
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            QMessageBox.warning(self, "任务查询失败", str(exc))
            return
        self.progress_bar.setValue(max(0, min(100, int(status.get("progress") or 0))))
        self.progress_label.setText(str(status.get("message") or status.get("stage") or "正在选品"))
        if status.get("status") == "success":
            self.selection_timer.stop()
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"选品完成，生成 {status.get('success_count') or 0} 个商品")
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.refresh()
        elif status.get("status") == "failed":
            self.selection_timer.stop()
            self.send_button.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.progress_label.setText("选品失败，积分已按后端结果处理")

    @staticmethod
    def _clear_row(row: QHBoxLayout) -> None:
        while row.count():
            child = row.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def refresh(self) -> None:
        search_items = self.gateway.user_search_results()
        derived_items = self.gateway.recommended_derived_products(10)
        new_items = self.gateway.daily_recommendations()
        self._clear_row(self.search_result_row)
        self._clear_row(self.derived_row)
        if search_items:
            for item in search_items[:10]:
                self.search_result_row.addWidget(StudioCompactCard(item, lambda current=item: self._show_report(current)))
        else:
            empty = QLabel("暂无搜索结果，输入需求后开始选品。")
            empty.setObjectName("Muted")
            self.search_result_row.addWidget(empty)
        if derived_items:
            for item in derived_items[:10]:
                self.derived_row.addWidget(StudioCompactCard(item, lambda current=item: self._show_report(current)))
        else:
            empty = QLabel("暂无衍生品，先在任务看板补齐衍生品。")
            empty.setObjectName("Muted")
            self.derived_row.addWidget(empty)
        while self.new_product_grid.count():
            child = self.new_product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, item in enumerate(new_items):
            card = StudioNewProductCard(item, index, self._show_report)
            self.new_product_grid.addWidget(card, index // 6, index % 6)
        self.new_product_grid.setColumnStretch(6, 1)

    def _show_report(self, item: dict[str, Any] | None) -> None:
        self.report_item = item
        while self.report_image_layout.count():
            child = self.report_image_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        while self.report_dimensions.count():
            child = self.report_dimensions.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if not item:
            self.report_product.setText("选择商品查看分析")
            self.report_summary.setText("选择商品后显示销量和综合参考")
            return
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        self.report_product.setText(f"{title[:32]}\n{format_jpy_price(price)}")
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(f"销量 {sales:,} · AI 参考 {float(score):.0f} 分")
        image = create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 278, 126)
        self.report_image_layout.addWidget(image)
        dimensions = dimension_items_from_report(item)
        if self.report_tab == "人群匹配":
            dimensions = [row for row in dimensions if row[0] in {"目标群体", "日本偏好", "竞品属性"}]
        elif self.report_tab == "使用场景":
            dimensions = [row for row in dimensions if row[0] in {"使用场景", "商品周期性", "复购属性"}]
        for name, level, content in dimensions:
            box = QFrame()
            box.setObjectName("StudioDimension")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 7, 10, 7)
            box_layout.setSpacing(2)
            line = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName("StudioDimensionName")
            grade = QLabel(level or "参考")
            grade.setObjectName("StudioDimensionGrade")
            line.addWidget(label)
            line.addStretch()
            line.addWidget(grade)
            box_layout.addLayout(line)
            detail = QLabel(content or "暂无分析内容")
            detail.setObjectName("StudioDimensionText")
            detail.setWordWrap(True)
            box_layout.addWidget(detail)
            self.report_dimensions.addWidget(box)

    def _select_report_tab(self, name: str, button: QPushButton) -> None:
        self.report_tab = name
        for tab in self.report_tab_buttons:
            tab.setChecked(tab is button)
        self._show_report(self.report_item)


class TeacherProductCard(QFrame):
    def __init__(self, product: dict[str, Any], on_open) -> None:
        super().__init__()
        self.product = product
        self.on_open = on_open
        self.setObjectName("TeacherProductCard")
        self.setMinimumSize(250, 410)
        self.setMaximumWidth(270)

        title = str(product.get("title") or "未命名原商品")
        price = product.get("price") or 0
        sales = int(float(product.get("sales_count") or 0))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(create_product_image(str(product.get("image_url") or ""), "📦", 230, 230))

        name = QLabel(title)
        name.setObjectName("ProductName")
        name.setWordWrap(True)
        name.setToolTip(title)
        name.setText(title[:14])
        layout.addWidget(name)

        metrics = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
        price_label.setObjectName("ProductPrice")
        sales_label = QLabel(f"销量 {sales:,} 个")
        sales_label.setObjectName("ProductMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)

        open_button = QPushButton("查看衍生品")
        open_button.setObjectName("PrimaryAction")
        open_button.clicked.connect(lambda: self.on_open(self.product))
        layout.addWidget(open_button)

    def metric_box(self, label: str, value: str) -> QWidget:
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


class AutoPublishSignals(QObject):
    created = Signal(dict)
    finished = Signal(dict)
    failed = Signal(str)


class AutoPublishTask(QRunnable):
    def __init__(self, gateway: DataGateway, payload: dict[str, Any], signals: AutoPublishSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.payload = payload
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            task = self.gateway.create_1688_auto_publish_task(self.payload)
            self.signals.created.emit(task)
            result = self.gateway.run_auto_publish_task(str(task["task_id"]))
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class AutoPublishPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.current_task: dict[str, Any] | None = None
        self.task_signals: AutoPublishSignals | None = None
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1500)
        self.progress_timer.timeout.connect(self.refresh_task_progress)
        self.layout.setContentsMargins(24, 22, 24, 22)
        self.layout.setSpacing(14)
        self.layout.addWidget(make_title("自动上架", "输入 1688 商品链接，抓取商品数据、优化信息、生成妙手模板并导入公用采集箱。"))

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setHorizontalSpacing(12)
        controls_layout.setVerticalSpacing(10)

        self.offer_url_input = QLineEdit()
        self.offer_url_input.setPlaceholderText("粘贴 1688 商品链接，例如 https://detail.1688.com/offer/xxxx.html")
        self.erp_input = QLineEdit("https://erp.91miaoshou.com/?ac=1og270")
        self.miaoshou_user_input = QLineEdit()
        self.miaoshou_user_input.setPlaceholderText("妙手手机号 / 子账号 / 邮箱")
        self.miaoshou_password_input = QLineEdit()
        self.miaoshou_password_input.setPlaceholderText("妙手密码")
        self.miaoshou_password_input.setEchoMode(QLineEdit.Password)
        self.dry_run = QCheckBox("仅生成模板")
        self.dry_run.setChecked(False)
        self.create_button = QPushButton("上架该产品")
        self.refresh_button = QPushButton("刷新")
        self.create_button.clicked.connect(self.create_1688_task)
        self.refresh_button.clicked.connect(self.refresh)

        controls_layout.addWidget(QLabel("1688 链接"), 0, 0)
        controls_layout.addWidget(self.offer_url_input, 0, 1, 1, 5)
        controls_layout.addWidget(QLabel("ERP 地址"), 1, 0)
        controls_layout.addWidget(self.erp_input, 1, 1, 1, 5)
        controls_layout.addWidget(QLabel("妙手账号"), 2, 0)
        controls_layout.addWidget(self.miaoshou_user_input, 2, 1, 1, 2)
        controls_layout.addWidget(QLabel("妙手密码"), 2, 3)
        controls_layout.addWidget(self.miaoshou_password_input, 2, 4, 1, 2)
        controls_layout.addWidget(self.dry_run, 3, 0, 1, 2)
        controls_layout.addWidget(self.refresh_button, 3, 4)
        controls_layout.addWidget(self.create_button, 3, 5)
        self.layout.addWidget(controls)

        progress_card = QFrame()
        progress_card.setObjectName("Card")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 12, 16, 12)
        self.progress_label = QLabel("待开始")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        self.layout.addWidget(progress_card)

        self.flow_table = table(["步骤", "状态"])
        fill_table(
            self.flow_table,
            [
                ["1. 调 Oxylabs 抓 1688 数据", "待执行"],
                ["2. AI 优化标题 / SKU / 描述", "待执行"],
                ["3. 生成妙手导入模板", "待执行"],
                ["4. 自动导入妙手公用采集箱", "待执行"],
            ],
        )
        self.layout.addWidget(self.flow_table, 1)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(150)
        self.result.setPlaceholderText("任务执行结果会显示在这里。")
        self.layout.addWidget(self.result)

    def activate(self) -> None:
        if not self.loaded:
            self.result.setPlaceholderText("粘贴 1688 商品链接后点击上架。长任务会在后台执行，窗口不会卡住。")
            self.loaded = True

    def refresh(self) -> None:
        self.reset_flow()
        self.result.clear()

    def create_task(self) -> None:
        if self.candidate_select.currentData() is None:
            QMessageBox.information(self, "暂无候选", "请先让老师通过至少一个衍生品。")
            return
        payload = {
            "derived_id": int(self.candidate_select.currentData()),
            "publish_count": 1,
            "target_channel": "TikTok Shop Japan",
            "erp_url": self.erp_input.text().strip() or "https://erp.91miaoshou.com/?ac=1og270",
            "dry_run": self.dry_run.isChecked(),
        }
        try:
            self.current_task = self.gateway.create_auto_publish_task(payload)
            self.render_result(self.current_task)
            QMessageBox.information(self, "任务已创建", "自动上架任务已创建。")
        except ApiError as exc:
            QMessageBox.warning(self, "创建失败", str(exc))

    def create_1688_task(self) -> None:
        offer_url = self.offer_url_input.text().strip()
        if not offer_url:
            QMessageBox.information(self, "请输入链接", "请先粘贴 1688 商品链接。")
            return
        payload = {
            "offer_url": offer_url,
            "publish_count": 1,
            "target_channel": "TikTok Shop Japan",
            "erp_url": self.erp_input.text().strip() or "https://erp.91miaoshou.com/?ac=1og270",
            "dry_run": self.dry_run.isChecked(),
            "miaoshou_username": self.miaoshou_user_input.text().strip(),
            "miaoshou_password": self.miaoshou_password_input.text().strip(),
        }
        self.start_background_task(payload)

    def start_background_task(self, payload: dict[str, Any]) -> None:
        self.create_button.setEnabled(False)
        self.create_button.setText("处理中...")
        self.progress_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在创建任务")
        self.result.setPlainText(
            "任务已开始，正在后台执行。\n\n"
            "这一步会调用 Oxylabs、百度图片翻译、必要时豆包补图、模板生成和妙手导入。\n"
            "如果弹出妙手浏览器，请在 10 分钟内手动输入验证码并登录。"
        )
        fill_table(
            self.flow_table,
            [
                ["1. 调 Oxylabs 抓 1688 数据", "处理中"],
                ["2. AI 优化标题 / SKU / 描述", "等待"],
                ["3. 生成妙手导入模板", "等待"],
                ["4. 自动导入妙手公用采集箱", "等待"],
            ],
        )
        self.task_signals = AutoPublishSignals()
        self.task_signals.created.connect(self.on_task_created)
        self.task_signals.finished.connect(self.on_task_finished)
        self.task_signals.failed.connect(self.on_task_failed)
        IMAGE_THREAD_POOL.start(AutoPublishTask(self.gateway, payload, self.task_signals))

    def on_task_created(self, task: dict[str, Any]) -> None:
        self.current_task = task
        self.apply_progress(task)
        self.progress_timer.start()

    def refresh_task_progress(self) -> None:
        if not self.current_task:
            return
        task_id = str(self.current_task.get("task_id") or "")
        if not task_id:
            return
        try:
            latest = self.gateway.get_auto_publish_task(task_id)
        except ApiError:
            return
        self.current_task = latest
        self.apply_progress(latest)

    def apply_progress(self, result: dict[str, Any]) -> None:
        progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
        percent = int(progress.get("percent") or 0)
        self.progress_bar.setValue(max(0, min(percent, 100)))
        message = str(progress.get("message") or result.get("message") or "任务处理中")
        current = progress.get("current")
        total = progress.get("total")
        if current is not None and total is not None and str(progress.get("stage") or "") == "images":
            message = f"{message}"
        self.progress_label.setText(message)
        stage = str(progress.get("stage") or "")
        if stage == "fetch":
            rows = [["1. 抓取 1688 数据", "处理中"], ["2. 优化标题 / SKU / 描述", "等待"], ["3. 生成图片 / 模板", "等待"], ["4. 导入妙手公用采集箱", "等待"]]
        elif stage == "copy":
            rows = [["1. 抓取 1688 数据", "完成"], ["2. 优化标题 / SKU / 描述", "处理中"], ["3. 生成图片 / 模板", "等待"], ["4. 导入妙手公用采集箱", "等待"]]
        elif stage in {"images", "template"}:
            rows = [["1. 抓取 1688 数据", "完成"], ["2. 优化标题 / SKU / 描述", "完成"], ["3. 生成图片 / 模板", "处理中"], ["4. 导入妙手公用采集箱", "等待"]]
        elif stage == "miaoshou":
            rows = [["1. 抓取 1688 数据", "完成"], ["2. 优化标题 / SKU / 描述", "完成"], ["3. 生成图片 / 模板", "完成"], ["4. 导入妙手公用采集箱", "处理中"]]
        elif stage == "done":
            rows = [["1. 抓取 1688 数据", "完成"], ["2. 优化标题 / SKU / 描述", "完成"], ["3. 生成图片 / 模板", "完成"], ["4. 导入妙手公用采集箱", "完成"]]
        else:
            rows = [["1. 抓取 1688 数据", "等待"], ["2. 优化标题 / SKU / 描述", "等待"], ["3. 生成图片 / 模板", "等待"], ["4. 导入妙手公用采集箱", "等待"]]
        fill_table(self.flow_table, rows)

    def on_task_finished(self, result: dict[str, Any]) -> None:
        self.progress_timer.stop()
        self.current_task = result
        self.apply_progress(result)
        self.render_result(result)
        self.create_button.setEnabled(True)
        self.create_button.setText("上架该产品")
        QMessageBox.information(self, "处理完成", result.get("message", "自动上架任务已执行。"))

    def on_task_failed(self, message: str) -> None:
        self.progress_timer.stop()
        self.progress_label.setText("任务失败")
        self.create_button.setEnabled(True)
        self.create_button.setText("上架该产品")
        QMessageBox.warning(self, "上架失败", message)

    def reset_flow(self) -> None:
        self.progress_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("待开始")
        fill_table(
            self.flow_table,
            [
                ["1. 调 Oxylabs 抓 1688 数据", "待执行"],
                ["2. AI 优化标题 / SKU / 描述", "待执行"],
                ["3. 生成妙手导入模板", "待执行"],
                ["4. 自动导入妙手公用采集箱", "待执行"],
            ],
        )

    def run_task(self) -> None:
        if not self.current_task:
            QMessageBox.information(self, "请先创建任务", "请选择候选衍生品并创建任务。")
            return
        try:
            result = self.gateway.run_auto_publish_task(str(self.current_task["task_id"]))
            self.current_task = result
            self.render_result(result)
            QMessageBox.information(self, "执行完成", result.get("message", "任务执行完成。"))
        except ApiError as exc:
            QMessageBox.warning(self, "执行失败", str(exc))

    def render_result(self, result: dict[str, Any]) -> None:
        flow_rows = [
            ["1. 调 Oxylabs 抓 1688 数据", "完成" if any("Oxylabs" in step or "1688" in step for step in result.get("steps", [])) else "待执行"],
            ["2. AI 优化标题 / SKU / 描述", "完成" if any("优化" in step for step in result.get("steps", [])) else "待执行"],
            ["3. 生成妙手导入模板", "完成" if result.get("template_path") else "待执行"],
            ["4. 自动导入妙手公用采集箱", "完成" if result.get("status") == "imported" else ("失败" if result.get("status") == "import_failed" else "待执行")],
        ]
        fill_table(self.flow_table, flow_rows)
        lines = [
            f"状态：{result.get('status', '-')}",
            f"消息：{result.get('message', '-')}",
            "",
            "步骤：",
        ]
        lines.extend([f"- {step}" for step in result.get("steps", [])])
        errors = result.get("errors") or []
        if errors:
            lines.append("")
            lines.append("错误：")
            lines.extend([f"- {error}" for error in errors])
        if result.get("template_path"):
            lines.append("")
            lines.append(f"模板文件：{result.get('template_path')}")
        import_result = result.get("import_result") or {}
        screenshots = import_result.get("screenshots") or []
        if screenshots:
            lines.append("")
            lines.append("失败截图：")
            lines.extend([f"- {path}" for path in screenshots])
        self.result.setPlainText("\n".join(lines))


class TeacherDashboardPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.setContentsMargins(24, 22, 24, 22)
        self.layout.setSpacing(18)
        header_bar = QFrame()
        header_bar.setObjectName("PageHeader")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(10)
        header_text = QVBoxLayout()
        header_text.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("教师看板")
        title.setObjectName("PageTitle")
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("IconButton")
        refresh_button.setFixedSize(54, 30)
        refresh_button.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh_button.setIconSize(QSize(16, 16))
        refresh_button.setToolTip("刷新教师看板数据")
        refresh_button.clicked.connect(self.force_refresh)
        self.refresh_button = refresh_button
        title_row.addWidget(title)
        title_row.addWidget(refresh_button)
        title_row.addStretch()
        subtitle = QLabel("点击原商品卡片查看 AI 衍生品，并对衍生品方向做拒绝原因批改。")
        subtitle.setObjectName("Muted")
        header_text.addLayout(title_row)
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text, 1)
        self.layout.addWidget(header_bar)

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
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(16)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def force_refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        try:
            self.refresh()
            self.loaded = True
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "刷新失败", str(exc))
        finally:
            self.refresh_button.setEnabled(True)

    def refresh(self) -> None:
        try:
            self.products = self.gateway.hot_products()
        except Exception as exc:
            self.products = []
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        total_derived = sum(int(item.get("derived_count") or 0) for item in self.products)
        total_pending = sum(int(item.get("pending_count") or 0) for item in self.products)
        self.source_metric.findChildren(QLabel)[1].setText(str(len(self.products)))
        self.derived_metric.findChildren(QLabel)[1].setText(str(total_derived))
        self.pending_metric.findChildren(QLabel)[1].setText(str(total_pending))
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        columns = 6
        for index, product in enumerate(self.products):
            self.grid.addWidget(TeacherProductCard(product, self.open_product), index // columns, index % columns)
        self.grid.setColumnStretch(columns, 1)
        self.grid.setRowStretch((len(self.products) // columns) + 1, 1)

    def open_product(self, product: dict[str, Any]) -> None:
        try:
            product_index = self.products.index(product)
        except ValueError:
            product_index = 0
        dialog = DerivedDialog(self.gateway, product, self.products, product_index, self)
        dialog.exec()
        self.refresh()


class DerivedDialog(QDialog):
    def __init__(self, gateway: DataGateway, product: dict[str, Any], products: list[dict[str, Any]] | None = None, product_index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.products = products or [product]
        self.product_index = max(0, min(product_index, len(self.products) - 1))
        self.product = product
        self.setWindowTitle(f"衍生品审核 - {self.product['title']}")
        self.resize(1120, 780)
        layout = QVBoxLayout(self)
        self.header = make_title(self.product["title"], "审核对象是 AI 衍生品，不是具体 1688 商品。")
        layout.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        wrap = QWidget()
        self.cards = QVBoxLayout(wrap)
        scroll.setWidget(wrap)
        layout.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("Toolbar")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 12, 14, 12)
        self.product_progress = QLabel()
        self.product_progress.setObjectName("Muted")
        next_button = QPushButton("下一个原商品")
        next_button.setObjectName("PrimaryAction")
        next_button.clicked.connect(self.next_product)
        footer_layout.addWidget(self.product_progress)
        footer_layout.addStretch()
        footer_layout.addWidget(next_button)
        layout.addWidget(footer)

        self.refresh_cards()

    def set_product(self, product: dict[str, Any]) -> None:
        self.product = product
        self.setWindowTitle(f"衍生品审核 - {self.product['title']}")
        title_label = self.header.findChild(QLabel, "PageTitle")
        if title_label:
            title_label.setText(str(self.product.get("title") or "未命名原商品"))
        self.refresh_cards()

    def next_product(self) -> None:
        if not self.products:
            return
        self.product_index = (self.product_index + 1) % len(self.products)
        self.set_product(self.products[self.product_index])

    def clear_cards(self) -> None:
        while self.cards.count():
            child = self.cards.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def refresh_cards(self) -> None:
        self.clear_cards()
        try:
            items = self.gateway.derived_products(self.product["id"])
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                items = []
            else:
                QMessageBox.warning(self, "加载失败", str(exc))
                items = []
        if not items:
            empty = QLabel("暂无衍生品，请先在任务看板补齐衍生品。")
            empty.setObjectName("Muted")
            self.cards.addWidget(empty)
        for item in items:
            self.cards.addWidget(self.card(item))
        self.cards.addStretch()
        self.product_progress.setText(f"原商品 {self.product_index + 1}/{len(self.products)}")

    def dimension_items(self, item: dict[str, Any]) -> list[tuple[str, str, str]]:
        return dimension_items_from_report(item)

    def card(self, item: dict[str, Any]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Card")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(12)

        image_url = str(item.get("supplier_image_url") or item.get("image_url") or self.product.get("image_url") or "")
        image = create_product_image(image_url, "📦", 150, 150)
        image.setFixedSize(158, 158)
        outer.addWidget(image, 0, Qt.AlignTop)

        layout = QVBoxLayout()
        layout.setSpacing(8)
        outer.addLayout(layout, 1)

        head = QHBoxLayout()
        title_text = str(item.get("derived_title") or item.get("title") or "未命名衍生品")
        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        title.setToolTip(title_text)
        title.setWordWrap(True)
        head.addWidget(title, 1)
        meta = QLabel(f"分数：{item.get('weighted_score')}   状态：{item.get('review_status')}")
        meta.setObjectName("Muted")
        head.addWidget(meta)
        head.addStretch()
        reject = QPushButton("拒绝")
        reject.clicked.connect(lambda: self.reject_item(item))
        head.addWidget(reject)
        layout.addLayout(head)

        dimensions = QGridLayout()
        dimensions.setHorizontalSpacing(8)
        dimensions.setVerticalSpacing(8)
        for index, (name, level, content) in enumerate(self.dimension_items(item)):
            box = QFrame()
            box.setObjectName("DimensionBox")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 7, 8, 7)
            box_layout.setSpacing(3)
            name_label = QLabel(name)
            name_label.setObjectName("DimensionTitle")
            level_label = QLabel(level or "-")
            level_label.setObjectName("DimensionLevel")
            content_label = QLabel(content[:42] if content else "暂无分析")
            content_label.setObjectName("DimensionText")
            content_label.setWordWrap(True)
            content_label.setToolTip(content)
            box_layout.addWidget(name_label)
            box_layout.addWidget(level_label)
            box_layout.addWidget(content_label)
            dimensions.addWidget(box, 0, index)
        dimensions.setColumnStretch(8, 1)
        layout.addLayout(dimensions)
        return frame

    def reject_item(self, item: dict[str, Any]) -> None:
        dialog = RejectDialog(self.gateway, item, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_cards()


class RejectDialog(QDialog):
    def __init__(self, gateway: DataGateway, item: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.item = item
        self.setWindowTitle("拒绝原因")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title = QLabel("拒绝原因")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        product = QLabel(str(item.get("derived_title") or "未命名衍生品"))
        product.setObjectName("Muted")
        product.setWordWrap(True)
        layout.addWidget(product)

        reason_box = QFrame()
        reason_box.setObjectName("FormPanel")
        reason_layout = QVBoxLayout(reason_box)
        reason_layout.setContentsMargins(16, 14, 16, 14)
        reason_layout.setSpacing(8)
        reason_label = QLabel("选择拒绝维度")
        reason_label.setObjectName("FormLabel")
        self.reason = QComboBox()
        self.reason.setObjectName("ReasonCombo")
        self.reason.setMinimumHeight(42)
        self.attributes = gateway.attributes()
        for attr in self.attributes:
            self.reason.addItem(attr["attribute_name"], attr["id"])
        reason_layout.addWidget(reason_label)
        reason_layout.addWidget(self.reason)
        layout.addWidget(reason_box)

        self.comment = QTextEdit()
        self.comment.setPlaceholderText("可填写补充说明")
        self.comment.setMinimumHeight(110)
        add = QPushButton("+ 新增属性原因")
        add.clicked.connect(self.add_attribute_hint)
        submit = QPushButton("确认拒绝")
        submit.setObjectName("PrimaryAction")
        submit.clicked.connect(self.submit)
        layout.addWidget(self.comment)
        actions = QHBoxLayout()
        actions.addWidget(add)
        actions.addStretch()
        actions.addWidget(submit)
        layout.addLayout(actions)

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
        "bg": "#f4f8fb",
        "sidebar": "#fbfdff",
        "panel": "#ffffff",
        "panel2": "#f8fbfd",
        "hero": "#f1fbf8",
        "input": "#f7fafc",
        "border": "#e1eaf0",
        "text": "#1f2a44",
        "muted": "#718096",
        "accent": "#159878",
        "accent_hover": "#0f8065",
        "tag": "#e7f7f1",
        "tag_text": "#147b67",
        "image_a": "#e9f5f2",
        "image_b": "#fff0ec",
        "metric": "#f2f7f9",
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
        #ReasonCombo {
            background: $panel; color: $text; border: 1px solid $accent;
            border-radius: 10px; padding: 9px 12px; font-size: 15px; font-weight: 800;
        }
        #ReasonCombo::drop-down {
            width: 34px; border: 0; border-left: 1px solid $border;
        }
        #DialogTitle {
            background: transparent; color: $text; font-size: 22px; font-weight: 900;
        }
        #FormPanel {
            background: $panel2; border: 1px solid $border; border-radius: 12px;
        }
        #FormLabel {
            background: transparent; color: $muted; font-size: 12px; font-weight: 800;
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
            background: transparent; color: $text; font-size: 15px; font-weight: 900;
        }
        #BrandSub {
            background: transparent; color: $muted; font-size: 11px; letter-spacing: 0px;
        }
        #SideNav {
            background: $sidebar; color: $muted; border: 0; padding: 14px;
            outline: 0; font-size: 15px;
        }
        #SideNav::item { height: 44px; border-radius: 9px; margin: 4px 8px; padding-left: 12px; }
        #SideNav::item:hover { background: $panel2; color: $text; }
        #SideNav::item:selected { background: $tag; color: $tag_text; }
        #UserBox {
            background: $panel2; border: 1px solid $border; border-radius: 12px;
            margin: 10px 12px 14px 12px;
        }
        #UserAvatar {
            background: $accent; color: #ffffff; border-radius: 17px;
            font-size: 14px; font-weight: 900;
        }
        #UserName {
            background: transparent; color: $text; font-size: 13px; font-weight: 800;
        }
        #UserRole {
            background: transparent; color: $muted; font-size: 11px;
        }
        #UserStatus {
            background: transparent; color: $muted; font-size: 11px; line-height: 1.35;
        }
        #SideLoginButton {
            background: $input; color: $text; border: 1px solid $border; border-radius: 8px;
            padding: 8px 12px; margin-top: 2px; font-weight: 700;
        }
        #SideLoginButton:hover { background: $accent_hover; color: #ffffff; }
        #IconButton {
            background: $panel; color: $accent; border: 1px solid $border;
            border-radius: 8px; font-size: 13px; font-weight: 800;
        }
        #IconButton:hover { background: $accent; color: #ffffff; }
        #Page { background: $bg; }
        #StudioHeader { background: transparent; }
        #StudioTitle { background: transparent; color: $text; font-size: 28px; font-weight: 900; }
        #StudioChat, #StudioReport {
            background: $panel; border: 1px solid $border; border-radius: 14px;
        }
        #StudioChat { background: $hero; }
        #StudioTutorial {
            background: $panel; color: $muted; border: 1px solid $border;
            border-radius: 8px; padding: 8px 12px; font-size: 11px; font-weight: 700;
        }
        #StudioTutorial:hover { color: $accent; border-color: $accent; }
        #StudioMarket { background: transparent; color: $muted; font-size: 11px; }
        #StudioBubbleUser, #StudioBubbleAi {
            border-radius: 8px; border: 1px solid $border;
        }
        #StudioBubbleUser { background: $tag; }
        #StudioBubbleAi { background: $panel; }
        #StudioBubbleText { background: transparent; color: $text; font-size: 12px; }
        #StudioPanelTitle { background: transparent; color: $text; font-size: 15px; font-weight: 900; }
        #StudioDot { background: transparent; color: #16a085; font-size: 16px; }
        #StudioPrimary {
            background: #ff6b6b; color: #ffffff; border: 0; border-radius: 8px;
            min-width: 112px; min-height: 38px; font-weight: 800;
        }
        #StudioPrimary:hover { background: #f05252; }
        #StudioChip {
            background: $panel; color: $muted; border: 1px solid $border;
            border-radius: 14px; padding: 5px 12px; font-size: 11px;
        }
        #StudioChip:hover { color: $accent; border-color: $accent; }
        #StudioIconButton {
            background: $panel; color: $accent; border: 1px solid $border; border-radius: 10px;
        }
        #StudioIconButton:hover { background: $accent; }
        #StudioSectionTitle { background: transparent; color: $text; font-size: 17px; font-weight: 900; }
        #StudioScroll { background: transparent; border: 0; }
        #StudioCarousel { background: transparent; }
        #StudioGrid { background: transparent; }
        #StudioReport { background: $panel2; }
        #StudioReportTitle { background: transparent; color: $text; font-size: 15px; font-weight: 900; line-height: 1.3; }
        #StudioDimension {
            background: $panel; border: 1px solid $border; border-radius: 8px;
        }
        #StudioDimensionName { background: transparent; color: $text; font-size: 11px; font-weight: 800; }
        #StudioDimensionGrade { background: transparent; color: $accent; font-size: 11px; font-weight: 800; }
        #StudioDimensionText { background: transparent; color: $muted; font-size: 10px; line-height: 1.25; }
        #StudioCarouselArrow {
            background: $panel; color: $accent; border: 1px solid $border; border-radius: 8px;
            font-size: 25px; font-weight: 700; padding: 0;
        }
        #StudioCarouselArrow:hover { background: $tag; border-color: $accent; }
        #StudioCompactCard {
            background: $panel; border: 1px solid $border; border-radius: 9px;
        }
        #StudioCompactCard:hover { border: 1px solid $accent; }
        #StudioCompactName { background: transparent; color: $text; font-size: 10px; font-weight: 800; }
        #StudioCompactPrice { background: transparent; color: #ef6461; font-size: 13px; font-weight: 900; }
        #StudioCompactMuted { background: transparent; color: $muted; font-size: 9px; }
        #StudioNewCard {
            background: $panel; border: 1px solid $border; border-radius: 10px;
        }
        #StudioNewCard:hover { border: 1px solid $accent; }
        #StudioNewName { background: transparent; color: $text; font-size: 12px; font-weight: 800; }
        #StudioNewTag {
            background: $tag; color: $tag_text; border-radius: 5px; padding: 3px 7px;
            font-size: 10px; font-weight: 700;
        }
        #StudioNewPrice { background: transparent; color: #ef6461; font-size: 17px; font-weight: 900; }
        #StudioNewMuted { background: transparent; color: $muted; font-size: 10px; }
        #StudioSummaryText { background: $panel; color: $muted; border-radius: 7px; padding: 7px 9px; font-size: 11px; }
        #StudioReportTab {
            background: transparent; color: $muted; border: 0; border-bottom: 2px solid transparent;
            border-radius: 0; padding: 7px 4px; font-size: 11px; font-weight: 700;
        }
        #StudioReportTab:checked { color: $tag_text; border-bottom: 2px solid $tag_text; }
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
        #DimensionBox {
            background: $panel2; border: 1px solid $border; border-radius: 8px;
            min-width: 92px; max-width: 116px; min-height: 92px;
        }
        #DimensionTitle {
            background: transparent; color: $text; font-size: 12px; font-weight: 900;
        }
        #DimensionLevel {
            background: transparent; color: $accent; font-size: 11px; font-weight: 800;
        }
        #DimensionText {
            background: transparent; color: $muted; font-size: 10px; line-height: 1.25;
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
        #ProductCarousel { background: $bg; }
        #CarouselNext {
            background: $panel; color: $accent; border: 1px solid $border;
            border-radius: 10px; font-size: 34px; font-weight: 800;
        }
        #CarouselNext:hover { background: $accent; color: #ffffff; }
        #ProductGridWrap { background: $bg; }
        #ProductCard, #TeacherProductCard, #CompactProductCard {
            background: $panel2; border: 1px solid $border; border-radius: 14px;
        }
        #ProductCard:hover, #TeacherProductCard:hover, #CompactProductCard:hover { border: 1px solid $accent; }
        #ProductImage, #TeacherProductImage { background: transparent; border-radius: 0; }
        #ProductIcon {
            background: transparent; font-size: 38px;
        }
        #ProductName {
            background: transparent; color: $text; font-size: 15px; font-weight: 800;
        }
        #CompactProductName {
            background: transparent; color: $text; font-size: 12px; font-weight: 800;
        }
        #CategoryTag {
            background: $tag; color: $tag_text; border-radius: 5px; padding: 4px 10px;
        }
        #ProductPrice {
            background: transparent; color: $accent; font-size: 20px; font-weight: 800;
        }
        #CompactProductPrice {
            background: transparent; color: $accent; font-size: 15px; font-weight: 800;
        }
        #ProductMuted {
            background: transparent; color: $muted;
        }
        #CompactProductMuted {
            background: transparent; color: $muted; font-size: 10px;
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
    app.setWindowIcon(QIcon(icon_path("10_TK跨境助手.ico")))
    apply_style(app)
    gateway = DataGateway()
    window = MainWindow(gateway)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
