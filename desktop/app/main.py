from __future__ import annotations

import sys
import json
import re
import time
from io import BytesIO
from pathlib import Path
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PIL import Image, ImageOps
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
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
    QRadioButton,
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
                else:
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
        return (
            "请重新登录" in str(exc)
            or "please log in again" in text
            or "http 401" in text
            or "invalid token" in text
            or "not authenticated" in text
            or "could not validate credentials" in text
        )

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

    def create_1688_batch_auto_publish_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/auto-publish/1688/batch-tasks", payload, timeout=60)

    def run_auto_publish_task(self, task_id: str) -> dict[str, Any]:
        return self.client.post(f"/api/auto-publish/tasks/{task_id}/run", timeout=1800)

    def start_auto_publish_task_async(self, task_id: str) -> dict[str, Any]:
        return self.client.post(f"/api/auto-publish/tasks/{task_id}/run-async", timeout=30)

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

    def video_projects(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/video/projects")

    def create_video_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/video/projects", payload)

    def update_video_project(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.put(f"/api/video/projects/{project_id}", payload)

    def upload_video_asset(self, project_id: int, file_path: str, fields: dict[str, Any]) -> dict[str, Any]:
        return self.client.upload(f"/api/video/projects/{project_id}/assets", file_path, fields, timeout=180)

    def update_video_asset(self, project_id: int, asset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.put(f"/api/video/projects/{project_id}/assets/{asset_id}", payload)

    def generate_video_script(self, project_id: int) -> dict[str, Any]:
        return self.client.post(f"/api/video/projects/{project_id}/script/generate", timeout=240)

    def save_video_script(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.put(f"/api/video/projects/{project_id}/script", payload)

    def create_video_task(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post(f"/api/video/projects/{project_id}/tasks", payload, timeout=300)

    def refresh_video_task(self, project_id: int, task_id: int) -> dict[str, Any]:
        return self.client.post(f"/api/video/projects/{project_id}/tasks/{task_id}/refresh", timeout=180)


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
        brand = QLabel("TK跨境助手")
        brand.setObjectName("BrandTitle")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand, 1)
        brand_sub = QLabel("Japan TikTok Selection")
        brand_sub.setObjectName("BrandSub")
        brand_layout.addLayout(brand_row)
        brand_layout.addWidget(brand_sub)

        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(220)
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

    def build_page_safely(self, factory) -> QWidget:
        try:
            return factory()
        except ApiError as exc:
            page = Page()
            page.layout.addWidget(make_title("请重新登录", f"服务器拒绝当前登录态：{exc}"))
            button = QPushButton("登录服务器账号")
            button.clicked.connect(self.open_login_dialog)
            page.layout.addWidget(button)
            page.layout.addStretch(1)
            return page

    def setup_pages(self) -> None:
        self.add_page("智能选品", self.build_page_safely(lambda: StudentSelectionPage(self.gateway)), "01_智能选品.ico")
        self.add_page("教师看板", self.build_page_safely(lambda: TeacherDashboardPage(self.gateway)), "02_教师看板.ico")
        self.add_page("任务看板", self.build_page_safely(lambda: PipelinePage(self.gateway)), "07_第三方API.ico")
        self.add_page("自动上架", self.build_page_safely(lambda: AutoPublishPage(self.gateway)), "10_TK跨境助手.ico")
        self.add_page("视频生成", self.build_page_safely(lambda: VideoGenerationPage(self.gateway)), "10_TK跨境助手.ico")
        self.add_page("用户管理", self.build_page_safely(lambda: AdminUsersPage(self.gateway)), "03_用户管理.ico")
        self.add_page("模型配置", self.build_page_safely(lambda: SimpleConfigPage("模型配置", self.gateway.model_configs, ["配置名称", "服务商", "类型", "Base URL", "模型", "Key", "状态", "默认"], self.gateway, "model")), "04_模型配置.ico")
        self.add_page("第三方 API", self.build_page_safely(lambda: SimpleConfigPage("第三方 API 配置", self.gateway.third_party_configs, ["配置名称", "服务类型", "API 地址", "Key", "状态"], self.gateway, "third")), "07_第三方API.ico")
        self.add_page("选品属性", self.build_page_safely(lambda: AttributePage(self.gateway)), "08_选品属性.ico")
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


class VideoScriptSignals(QObject):
    finished = Signal(dict)
    failed = Signal(str)


class VideoScriptTask(QRunnable):
    def __init__(self, gateway: DataGateway, project_id: int, signals: VideoScriptSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.project_id = project_id
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.gateway.generate_video_script(self.project_id))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class VideoTaskSignals(QObject):
    finished = Signal(dict)
    failed = Signal(str)


class VideoSubmitTask(QRunnable):
    def __init__(self, gateway: DataGateway, project_id: int, payload: dict[str, Any], signals: VideoTaskSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.project_id = project_id
        self.payload = payload
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.gateway.create_video_task(self.project_id, self.payload))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class VideoRefreshTask(QRunnable):
    def __init__(self, gateway: DataGateway, project_id: int, task_id: int, signals: VideoTaskSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.project_id = project_id
        self.task_id = task_id
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.gateway.refresh_video_task(self.project_id, self.task_id))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class VideoGenerationPage(Page):
    VIDEO_STRATEGY_OPTIONS = [
        ("自动稳妥", "auto_safe"),
        ("静态展示：适合复杂结构/带线/带屏商品", "static_display"),
        ("轻交互：只允许手指触摸/指向", "light_interaction"),
        ("手持演示：适合简单小件商品", "handheld_demo"),
        ("佩戴演示：仅适合服饰/首饰/帽子等", "wearable_demo"),
    ]

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.current_project: dict[str, Any] | None = None
        self.video_task_busy = False
        self.video_refresh_busy = False
        self.video_poll_timer = QTimer(self)
        self.video_poll_timer.setInterval(8000)
        self.video_poll_timer.timeout.connect(self.auto_refresh_video_task)
        self.layout.addWidget(make_title("视频生成", "上传产品图，生成脚本，再提交视频。产品图会作为强参考。"))
        body = QHBoxLayout()
        self.step_nav = QListWidget()
        self.step_nav.setObjectName("SideNav")
        self.step_nav.setFixedWidth(190)
        for name in ["1 产品信息", "2 产品图片", "3 视频脚本", "4 生成视频"]:
            self.step_nav.addItem(QListWidgetItem(name))
        self.stack = QStackedWidget()
        self.step_nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        body.addWidget(self.step_nav)
        body.addWidget(self.stack, 1)
        self.layout.addLayout(body, 1)
        self.build_info_step()
        self.build_assets_step()
        self.build_script_step()
        self.build_generate_step()
        self.step_nav.setCurrentRow(0)

    def hint(self, title: str, text: str) -> QWidget:
        box = QFrame()
        box.setObjectName("PromptHint")
        layout = QVBoxLayout(box)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        text_label = QLabel(text)
        text_label.setObjectName("Muted")
        text_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        return box

    def activate(self) -> None:
        if not self.loaded:
            self.refresh_projects()
            self.loaded = True

    def build_info_step(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.hint("第 1 步：填写产品信息", "产品详情用中文填写；字幕/口播语言默认日语。"))
        grid = QGridLayout()
        self.video_title = QLineEdit()
        self.video_title.setPlaceholderText("项目标题")
        self.market = QComboBox()
        self.market.setEditable(True)
        self.market.addItems(["日本", "美国", "英国", "东南亚", "韩国"])
        self.language = QComboBox()
        self.language.setEditable(True)
        self.language.addItems(["日语", "英语", "中文", "韩语", "泰语"])
        self.video_strategy = QComboBox()
        for label, key in self.VIDEO_STRATEGY_OPTIONS:
            self.video_strategy.addItem(label, key)
        self.product_details = QTextEdit()
        self.product_details.setMinimumHeight(150)
        self.product_details.setPlaceholderText("粘贴产品详情、卖点、人群、场景、风格要求。")
        grid.addWidget(QLabel("项目标题"), 0, 0)
        grid.addWidget(self.video_title, 0, 1)
        grid.addWidget(QLabel("目标市场"), 0, 2)
        grid.addWidget(self.market, 0, 3)
        grid.addWidget(QLabel("字幕/口播语言"), 0, 4)
        grid.addWidget(self.language, 0, 5)
        grid.addWidget(QLabel("产品详情"), 1, 0)
        grid.addWidget(self.product_details, 1, 1, 1, 5)
        grid.addWidget(QLabel("拍摄方案"), 2, 0)
        grid.addWidget(self.video_strategy, 2, 1, 1, 5)
        layout.addLayout(grid)
        actions = QHBoxLayout()
        create = QPushButton("保存为新项目")
        save = QPushButton("保存当前产品信息")
        create.clicked.connect(self.create_project)
        save.clicked.connect(lambda: self.save_project(False))
        actions.addWidget(create)
        actions.addWidget(save)
        actions.addStretch()
        layout.addLayout(actions)
        self.project_table = table(["ID", "项目", "市场", "语言", "状态"])
        self.project_table.doubleClicked.connect(self.load_selected_project)
        layout.addWidget(self.project_table, 1)
        self.stack.addWidget(page)

    def build_assets_step(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.hint("第 2 步：上传产品图", "建议 2-5 张。至少上传一张清晰产品主图。"))
        row = QHBoxLayout()
        self.asset_role = QLineEdit()
        self.asset_role.setPlaceholderText("图片角色：主图/细节图/场景图")
        self.asset_desc = QLineEdit()
        self.asset_desc.setPlaceholderText("图片说明：这张图代表什么")
        self.primary_asset = QCheckBox("主参考图")
        upload = QPushButton("上传产品图")
        save_asset = QPushButton("保存图片说明")
        upload.clicked.connect(self.upload_assets)
        save_asset.clicked.connect(self.save_selected_asset)
        row.addWidget(self.asset_role)
        row.addWidget(self.asset_desc, 1)
        row.addWidget(self.primary_asset)
        row.addWidget(save_asset)
        row.addWidget(upload)
        layout.addLayout(row)
        self.asset_table = table(["ID", "角色", "说明", "主图", "地址"])
        self.asset_table.itemSelectionChanged.connect(self.load_selected_asset)
        layout.addWidget(self.asset_table, 1)
        self.stack.addWidget(page)

    def build_script_step(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.hint("第 3 步：生成并修改脚本", "中文脚本说明，日语字幕/口播。生成时有进度条，窗口不会卡住。"))
        actions = QHBoxLayout()
        self.generate_script_button = QPushButton("AI 生成脚本")
        self.save_script_button = QPushButton("保存修改后的脚本")
        self.generate_script_button.clicked.connect(self.generate_script)
        self.save_script_button.clicked.connect(lambda: self.save_script(False))
        actions.addWidget(self.generate_script_button)
        actions.addWidget(self.save_script_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.script_progress = QProgressBar()
        self.script_progress.setRange(0, 0)
        self.script_progress.hide()
        self.script_progress_label = QLabel("正在请求 AI 生成脚本，请稍候...")
        self.script_progress_label.setObjectName("Muted")
        self.script_progress_label.hide()
        layout.addWidget(self.script_progress)
        layout.addWidget(self.script_progress_label)
        self.script_text = QTextEdit()
        self.script_text.setMinimumHeight(130)
        layout.addWidget(self.script_text)
        self.shot_table = table(["时间轴", "景别", "中文画面", "日语字幕/口播", "中文氛围与画质"])
        self.shot_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        layout.addWidget(self.shot_table, 1)
        self.stack.addWidget(page)

    def build_generate_step(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.hint("第 4 步：生成视频", "系统会用产品图、分镜画面和脚本生成视频。产品图优先级最高。"))
        row = QHBoxLayout()
        self.image_mode_label = QLabel("产品参考视频")
        self.image_mode_label.setObjectName("CardTitle")
        self.video_model = QComboBox()
        self.video_model.addItem("Seedance 2.0 mini", "doubao-seedance-2-0-mini-260615")
        self.video_model.addItem("Seedance 2.0 Fast", "doubao-seedance-2-0-fast")
        self.submit_video_button = QPushButton("提交生成视频")
        self.refresh_task_button = QPushButton("刷新任务")
        self.download_video_button = QPushButton("下载视频")
        self.submit_video_button.clicked.connect(self.create_video_task)
        self.refresh_task_button.clicked.connect(self.refresh_selected_video_task)
        self.download_video_button.clicked.connect(self.download_current_video)
        row.addWidget(self.image_mode_label)
        row.addWidget(self.video_model)
        row.addWidget(self.submit_video_button)
        row.addWidget(self.refresh_task_button)
        row.addWidget(self.download_video_button)
        row.addStretch()
        layout.addLayout(row)

        content = QHBoxLayout()
        left = QVBoxLayout()
        self.generate_status = QLabel("准备就绪：确认脚本和产品图后提交。")
        self.generate_status.setObjectName("Muted")
        self.generate_status.setWordWrap(True)
        left.addWidget(self.generate_status)
        self.video_progress = QProgressBar()
        self.video_progress.setRange(0, 0)
        self.video_progress.hide()
        self.video_progress_label = QLabel("模型任务已提交，正在生成中；页面会自动刷新状态。")
        self.video_progress_label.setObjectName("Muted")
        self.video_progress_label.setWordWrap(True)
        self.video_progress_label.hide()
        left.addWidget(self.video_progress)
        left.addWidget(self.video_progress_label)
        self.video_storage_label = QLabel("存放位置：-")
        self.video_storage_label.setObjectName("Muted")
        self.video_storage_label.setWordWrap(True)
        left.addWidget(self.video_storage_label)
        self.video_usage_label = QLabel("消耗：-")
        self.video_usage_label.setObjectName("Muted")
        self.video_usage_label.setWordWrap(True)
        left.addWidget(self.video_usage_label)
        self.task_table = table(["任务ID", "状态", "消耗", "结果"])
        self.task_table.setMaximumHeight(190)
        self.task_table.itemSelectionChanged.connect(self.preview_selected_task)
        left.addWidget(self.task_table)
        self.video_result = QTextEdit()
        self.video_result.setReadOnly(True)
        self.video_result.setMaximumHeight(120)
        self.video_result.setPlaceholderText("任务摘要会显示在这里。")
        left.addWidget(self.video_result)

        preview = QVBoxLayout()
        preview_title = QLabel("视频预览")
        preview_title.setObjectName("CardTitle")
        self.video_preview_status = QLabel("生成完成后会在这里播放 9:16 视频。")
        self.video_preview_status.setObjectName("Muted")
        self.video_preview_status.setWordWrap(True)
        self.video_widget = QVideoWidget()
        self.video_widget.setFixedSize(300, 533)
        self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        self.video_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.video_player.setAudioOutput(self.audio_output)
        self.video_player.setVideoOutput(self.video_widget)
        self.current_video_url = ""
        self.current_video_storage = ""
        preview.addWidget(preview_title)
        preview.addWidget(self.video_preview_status)
        preview.addWidget(self.video_widget, 0, Qt.AlignHCenter)
        preview.addStretch(1)

        content.setSpacing(22)
        content.addLayout(left, 2)
        content.addLayout(preview, 1)
        layout.addLayout(content, 1)
        self.stack.addWidget(page)

    def strategy_label(self) -> str:
        return self.video_strategy.currentText().strip() or "自动稳妥"

    def split_strategy_details(self, text: str) -> tuple[str, str]:
        strategy = "自动稳妥"
        cleaned_lines: list[str] = []
        labels = {label for label, _ in self.VIDEO_STRATEGY_OPTIONS}
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if line.startswith("拍摄方案：") or line.startswith("拍摄方案:"):
                value = re.split(r"[:：]", line, maxsplit=1)[-1].strip()
                if value in labels:
                    strategy = value
                continue
            if line.startswith("video_strategy_key:"):
                continue
            cleaned_lines.append(raw_line)
        return strategy, "\n".join(cleaned_lines).strip()

    def set_strategy_label(self, label: str) -> None:
        for index in range(self.video_strategy.count()):
            if self.video_strategy.itemText(index) == label:
                self.video_strategy.setCurrentIndex(index)
                return
        self.video_strategy.setCurrentIndex(0)

    def payload(self) -> dict[str, Any]:
        _, details = self.split_strategy_details(self.product_details.toPlainText())
        strategy = self.strategy_label()
        strategy_key = self.video_strategy.currentData() or "auto_safe"
        if details:
            details = f"video_strategy_key:{strategy_key}\n拍摄方案：{strategy}\n{details}"
        else:
            details = f"video_strategy_key:{strategy_key}\n拍摄方案：{strategy}"
        return {
            "title": self.video_title.text().strip() or "未命名视频项目",
            "target_market": self.market.currentText().strip() or "日本",
            "video_language": self.language.currentText().strip() or "日语",
            "product_details": details,
        }

    def create_project(self) -> None:
        try:
            self.current_project = self.gateway.create_video_project(self.payload())
            self.refresh_projects()
            self.load_project(self.current_project)
            self.step_nav.setCurrentRow(1)
        except Exception as exc:
            QMessageBox.warning(self, "创建失败", str(exc))

    def save_project(self, silent: bool = False) -> bool:
        if not self.current_project:
            self.create_project()
            return bool(self.current_project)
        try:
            self.current_project = self.gateway.update_video_project(int(self.current_project["id"]), self.payload())
            if not silent:
                QMessageBox.information(self, "保存成功", "产品信息已保存。")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False

    def refresh_projects(self) -> None:
        try:
            self.projects = self.gateway.video_projects()
        except Exception:
            self.projects = []
        fill_table(self.project_table, [[p.get("id"), p.get("title"), p.get("target_market"), p.get("video_language"), p.get("status")] for p in self.projects])

    def load_selected_project(self) -> None:
        row = self.project_table.currentRow()
        if hasattr(self, "projects") and 0 <= row < len(self.projects):
            self.current_project = self.projects[row]
            self.load_project(self.current_project)

    def load_project(self, project: dict[str, Any]) -> None:
        self.video_title.setText(str(project.get("title") or ""))
        self.market.setEditText(str(project.get("target_market") or "日本"))
        self.language.setEditText(str(project.get("video_language") or "日语"))
        strategy, details = self.split_strategy_details(str(project.get("product_details") or ""))
        self.set_strategy_label(strategy)
        self.product_details.setPlainText(details)
        self.render_assets()
        self.render_script()
        self.refresh_generate_summary()

    def render_assets(self) -> None:
        assets = (self.current_project or {}).get("assets") or []
        rows = []
        for asset in assets:
            if asset.get("asset_type") not in {"product", "product_image", ""}:
                continue
            rows.append([
                asset.get("id"),
                asset.get("role"),
                asset.get("description"),
                "是" if asset.get("is_primary") else "-",
                asset.get("public_url") or asset.get("url"),
            ])
        fill_table(self.asset_table, rows)

    def selected_asset(self) -> dict[str, Any] | None:
        row = self.asset_table.currentRow()
        if row < 0:
            return None
        asset_id_item = self.asset_table.item(row, 0)
        if not asset_id_item:
            return None
        asset_id = int(asset_id_item.text() or 0)
        for asset in (self.current_project or {}).get("assets") or []:
            if int(asset.get("id") or 0) == asset_id:
                return asset
        return None

    def load_selected_asset(self) -> None:
        asset = self.selected_asset()
        if not asset:
            return
        self.asset_role.setText(str(asset.get("role") or ""))
        self.asset_desc.setText(str(asset.get("description") or ""))
        self.primary_asset.setChecked(bool(asset.get("is_primary")))

    def save_selected_asset(self) -> None:
        if not self.current_project:
            return
        asset = self.selected_asset()
        if not asset:
            QMessageBox.information(self, "提示", "请先选中下面要修改的图片。")
            return
        try:
            self.current_project = self.gateway.update_video_asset(
                int(self.current_project["id"]),
                int(asset["id"]),
                {
                    "role": self.asset_role.text().strip(),
                    "description": self.asset_desc.text().strip(),
                    "is_primary": 1 if self.primary_asset.isChecked() else 0,
                },
            )
            self.render_assets()
            QMessageBox.information(self, "保存成功", "图片说明已同步到选中图片。")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def upload_assets(self) -> None:
        if not self.current_project:
            self.create_project()
        if not self.current_project:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "选择产品图", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not files:
            return
        for index, path in enumerate(files):
            self.current_project = self.gateway.upload_video_asset(
                int(self.current_project["id"]),
                path,
                {"role": self.asset_role.text(), "description": self.asset_desc.text(), "is_primary": 1 if self.primary_asset.isChecked() and index == 0 else 0},
            )
        self.render_assets()
        QMessageBox.information(self, "上传完成", f"已上传 {len(files)} 张产品图。")

    def generate_script(self) -> None:
        if not self.current_project:
            self.create_project()
        elif not self.save_project(True):
            return
        if not self.current_project:
            return
        self.generate_script_button.setEnabled(False)
        self.save_script_button.setEnabled(False)
        self.script_progress.show()
        self.script_progress_label.show()
        self.script_signals = VideoScriptSignals()
        self.script_signals.finished.connect(self.on_script_generated)
        self.script_signals.failed.connect(self.on_script_failed)
        IMAGE_THREAD_POOL.start(VideoScriptTask(self.gateway, int(self.current_project["id"]), self.script_signals))

    def on_script_generated(self, project: dict[str, Any]) -> None:
        self.current_project = project
        self.generate_script_button.setEnabled(True)
        self.save_script_button.setEnabled(True)
        self.script_progress.hide()
        self.script_progress_label.hide()
        self.render_script()
        QMessageBox.information(self, "脚本已生成", "脚本说明为中文，字幕/口播为日语。")

    def on_script_failed(self, message: str) -> None:
        self.generate_script_button.setEnabled(True)
        self.save_script_button.setEnabled(True)
        self.script_progress.hide()
        self.script_progress_label.hide()
        QMessageBox.warning(self, "生成失败", message)

    def render_script(self) -> None:
        if not self.current_project:
            return
        script_text = str(self.current_project.get("script_text") or "")
        self.script_text.setPlainText(script_text)
        self.shot_table.setRowCount(0)
        for shot in self.normalized_storyboard(script_text):
            row = self.shot_table.rowCount()
            self.shot_table.insertRow(row)
            for col, key in enumerate(["timeline", "shot_type", "visual_cn", "copy", "atmosphere_cn"]):
                self.shot_table.setItem(row, col, QTableWidgetItem(str(shot.get(key) or "")))

    def normalized_storyboard(self, script_text: str = "") -> list[dict[str, str]]:
        if not self.current_project:
            return []
        raw = self.current_project.get("storyboard") or []
        if not raw:
            script_json = self.current_project.get("script_json") or {}
            if isinstance(script_json, str):
                try:
                    script_json = json.loads(script_json or "{}")
                except ValueError:
                    script_json = {}
            if isinstance(script_json, dict):
                raw = script_json.get("storyboard") or script_json.get("shot_list") or []
        shots = [self.normalize_shot(item) for item in raw if isinstance(item, dict)]
        if shots:
            return shots
        return self.parse_shots_from_text(script_text)

    def normalize_shot(self, shot: dict[str, Any]) -> dict[str, str]:
        return {
            "timeline": str(shot.get("timeline") or shot.get("time") or shot.get("time_range") or ""),
            "shot_type": str(shot.get("shot_type") or shot.get("shot_size") or shot.get("shot") or ""),
            "visual_cn": str(shot.get("visual_cn") or shot.get("visual") or shot.get("image") or ""),
            "copy": str(shot.get("copy") or shot.get("subtitle") or shot.get("voiceover") or ""),
            "atmosphere_cn": str(shot.get("atmosphere_cn") or shot.get("atmosphere_quality") or shot.get("quality") or ""),
        }

    def parse_shots_from_text(self, script_text: str) -> list[dict[str, str]]:
        shots: list[dict[str, str]] = []
        for line in script_text.splitlines():
            if not re.match(r"^\s*\d+\s*-\s*\d+\s*s", line):
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3:
                continue
            shot = {
                "timeline": parts[0],
                "shot_type": parts[1] if len(parts) > 1 else "",
                "visual_cn": "",
                "copy": "",
                "atmosphere_cn": "",
            }
            for part in parts[2:]:
                text = part.strip()
                if text.startswith("画面：") or text.startswith("画面:"):
                    shot["visual_cn"] = re.sub(r"^画面[:：]\s*", "", text)
                elif text.startswith("字幕/口播：") or text.startswith("字幕/口播:"):
                    shot["copy"] = re.sub(r"^字幕/口播[:：]\s*", "", text)
                elif text.startswith("氛围与画质：") or text.startswith("氛围与画质:"):
                    shot["atmosphere_cn"] = re.sub(r"^氛围与画质[:：]\s*", "", text)
                elif not shot["visual_cn"]:
                    shot["visual_cn"] = text
            shots.append(shot)
        return shots

    def script_payload(self) -> dict[str, Any]:
        shots = []
        for row in range(self.shot_table.rowCount()):
            values = [self.shot_table.item(row, col).text().strip() if self.shot_table.item(row, col) else "" for col in range(5)]
            if any(values):
                shots.append({"timeline": values[0], "shot_type": values[1], "visual_cn": values[2], "copy": values[3], "atmosphere_cn": values[4]})
        return {"script_text": self.script_text.toPlainText().strip(), "storyboard": shots}

    def save_script(self, silent: bool = False) -> bool:
        if not self.current_project:
            return False
        try:
            self.current_project = self.gateway.save_video_script(int(self.current_project["id"]), self.script_payload())
            self.refresh_generate_summary()
            if not silent:
                QMessageBox.information(self, "保存成功", "脚本已保存。")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False

    def task_is_active(self, task: dict[str, Any] | None) -> bool:
        if not task:
            return False
        status = str(task.get("status") or "").lower()
        return status in {"submitted", "running", "queued", "pending", "processing", "in_progress"}

    def set_video_progress(self, active: bool, text: str = "") -> None:
        if not hasattr(self, "video_progress"):
            return
        if active:
            self.video_progress.show()
            self.video_progress_label.show()
            self.video_progress_label.setText(text or "模型任务已提交，正在生成中；页面会自动刷新状态。")
        else:
            self.video_progress.hide()
            self.video_progress_label.hide()

    def set_video_buttons_busy(self, busy: bool) -> None:
        self.video_task_busy = busy
        if hasattr(self, "submit_video_button"):
            self.submit_video_button.setEnabled(not busy)
        if hasattr(self, "refresh_task_button"):
            self.refresh_task_button.setEnabled(not busy)

    def selected_or_latest_task(self) -> dict[str, Any] | None:
        if not self.current_project:
            return None
        tasks = self.current_project.get("tasks") or []
        if not tasks:
            return None
        row = self.task_table.currentRow() if hasattr(self, "task_table") else -1
        if row >= 0:
            task_id_item = self.task_table.item(row, 0)
            task_id = int(task_id_item.text() or 0) if task_id_item else 0
            selected = next((item for item in tasks if int(item.get("id") or 0) == task_id), None)
            if selected:
                return selected
        return tasks[0]

    def create_video_task(self) -> None:
        if not self.current_project or not self.save_script(True):
            return
        product_assets = [asset for asset in (self.current_project.get("assets") or []) if asset.get("asset_type") in {"product", "product_image"}]
        if not product_assets:
            QMessageBox.information(self, "提示", "请先上传至少 1 张产品图，再生成视频。")
            return
        mode = "image_to_video"
        payload = {"generation_mode": mode, "model_name": str(self.video_model.currentData() or self.video_model.currentText()).strip()}
        self.generate_status.setText("正在提交给视频模型。系统会先生成分镜画面，请稍候。")
        self.set_video_progress(True, "正在调用视频模型，任务创建中...")
        self.set_video_buttons_busy(True)
        self.video_submit_signals = VideoTaskSignals()
        self.video_submit_signals.finished.connect(self.on_video_task_created)
        self.video_submit_signals.failed.connect(self.on_video_task_failed)
        IMAGE_THREAD_POOL.start(VideoSubmitTask(self.gateway, int(self.current_project["id"]), payload, self.video_submit_signals))

    def on_video_task_created(self, task: dict[str, Any]) -> None:
        self.set_video_buttons_busy(False)
        self.video_result.setPlainText(self.video_task_summary(task))
        if self.current_project is not None:
            tasks = self.current_project.setdefault("tasks", [])
            tasks.insert(0, task)
        self.refresh_generate_summary()
        self.preview_task_video(task)
        if self.task_is_active(task):
            self.generate_status.setText(f"视频任务已提交，模型正在生成。任务号：{task.get('provider_task_id') or task.get('id')}")
            self.set_video_progress(True, "模型正在生成视频，系统会自动刷新任务状态。")
            self.video_poll_timer.start()
        else:
            self.set_video_progress(False)

    def on_video_task_failed(self, message: str) -> None:
        self.set_video_buttons_busy(False)
        self.set_video_progress(False)
        self.generate_status.setText("提交失败，请检查模型配置、第三方 API 和余额。")
        QMessageBox.warning(self, "提交失败", message)

    def refresh_selected_video_task(self) -> None:
        if not self.current_project:
            QMessageBox.information(self, "提示", "请先选择一个视频项目。")
            return
        task = self.selected_or_latest_task()
        if not task:
            QMessageBox.information(self, "提示", "当前项目还没有视频任务。")
            return
        self.start_video_refresh(task, manual=True)

    def start_video_refresh(self, task: dict[str, Any], manual: bool = False) -> None:
        if self.video_refresh_busy or self.video_task_busy or not self.current_project:
            return
        self.video_refresh_busy = True
        if manual:
            self.generate_status.setText("正在刷新视频任务结果和 token 消耗。")
        if self.task_is_active(task):
            self.set_video_progress(True, "模型正在生成视频，系统会自动刷新任务状态。")
        self.video_refresh_signals = VideoTaskSignals()
        self.video_refresh_signals.finished.connect(self.on_video_task_refreshed)
        self.video_refresh_signals.failed.connect(lambda message: self.on_video_refresh_failed(message, manual))
        IMAGE_THREAD_POOL.start(VideoRefreshTask(self.gateway, int(self.current_project["id"]), int(task["id"]), self.video_refresh_signals))

    def on_video_task_refreshed(self, refreshed: dict[str, Any]) -> None:
        self.video_refresh_busy = False
        tasks = self.current_project.get("tasks") if self.current_project else []
        if tasks is not None:
            for index, item in enumerate(tasks):
                if int(item.get("id") or 0) == int(refreshed.get("id") or 0):
                    tasks[index] = refreshed
                    break
            else:
                tasks.insert(0, refreshed)
        self.video_result.setPlainText(self.video_task_summary(refreshed))
        self.refresh_generate_summary()
        self.preview_task_video(refreshed)
        status = str(refreshed.get("status") or "")
        if self.task_is_active(refreshed):
            self.generate_status.setText(f"视频生成中：{status or 'running'}。任务号：{refreshed.get('provider_task_id') or refreshed.get('id')}")
            self.set_video_progress(True, "模型正在生成视频，系统会自动刷新任务状态。")
            self.video_poll_timer.start()
        else:
            self.video_poll_timer.stop()
            self.set_video_progress(False)
            if refreshed.get("video_url") or refreshed.get("result_video_url") or refreshed.get("local_video_url"):
                self.generate_status.setText("视频生成完成，可以预览或下载。")
            elif str(refreshed.get("status") or "").lower() in {"failed", "cancelled", "canceled"}:
                self.generate_status.setText(f"视频生成失败：{refreshed.get('error_message') or refreshed.get('status')}")
            else:
                self.generate_status.setText(f"任务状态：{refreshed.get('status') or '-'}")

    def on_video_refresh_failed(self, message: str, manual: bool = False) -> None:
        self.video_refresh_busy = False
        if manual:
            self.generate_status.setText("刷新失败，请检查状态查询接口配置和任务状态。")
            QMessageBox.warning(self, "刷新失败", message)

    def auto_refresh_video_task(self) -> None:
        task = self.selected_or_latest_task()
        if not task or not self.task_is_active(task):
            self.video_poll_timer.stop()
            self.set_video_progress(False)
            return
        self.start_video_refresh(task, manual=False)

    def refresh_generate_summary(self) -> None:
        if not hasattr(self, "task_table"):
            return
        project = self.current_project or {}
        assets = project.get("assets") or []
        product_assets = [asset for asset in assets if asset.get("asset_type") in {"product", "product_image"}]
        storyboard_assets = [asset for asset in assets if asset.get("asset_type") == "storyboard_sheet"]
        storyboard = project.get("storyboard") or []
        script_ready = bool(str(project.get("script_text") or "").strip() or storyboard)
        sheet_text = "已有分镜画面" if storyboard_assets else "提交后会先自动生成分镜画面"
        self.generate_status.setText(f"脚本{'已准备' if script_ready else '未准备'}，产品图 {len(product_assets)} 张，{sheet_text}。产品图会作为最高优先级参考。")
        task_rows = []
        for task in project.get("tasks") or []:
            task_rows.append([
                task.get("id"),
                task.get("status"),
                self.video_usage_text(task, compact=True),
                self.video_result_text(task),
            ])
        fill_table(self.task_table, task_rows)
        self.preview_task_video(self.latest_video_task())
        active_task = next((task for task in project.get("tasks") or [] if self.task_is_active(task)), None)
        if active_task:
            self.generate_status.setText(f"视频生成中：{active_task.get('status') or 'running'}。任务号：{active_task.get('provider_task_id') or active_task.get('id')}")
            self.set_video_progress(True, "模型正在生成视频，系统会自动刷新任务状态。")
            if not self.video_poll_timer.isActive():
                self.video_poll_timer.start()
        elif hasattr(self, "video_poll_timer") and self.video_poll_timer.isActive():
            self.video_poll_timer.stop()
            self.set_video_progress(False)

    def latest_video_task(self) -> dict[str, Any]:
        project = self.current_project or {}
        for task in project.get("tasks") or []:
            if task.get("video_url") or task.get("result_video_url") or task.get("local_video_url") or task.get("local_video_path"):
                return task
        if project.get("result_video_url"):
            return {"video_url": project.get("result_video_url"), "result_video_url": project.get("result_video_url")}
        return {}

    def video_storage_text(self, task: dict[str, Any]) -> str:
        return str(
            task.get("local_video_path")
            or task.get("local_video_url")
            or task.get("video_url")
            or task.get("result_video_url")
            or ""
        )

    def video_result_text(self, task: dict[str, Any]) -> str:
        if task.get("error_message"):
            return str(task.get("error_message"))
        if task.get("video_url") or task.get("result_video_url") or task.get("local_video_url") or task.get("local_video_path"):
            return "已生成，可预览/下载"
        if task.get("provider_task_id"):
            return f"任务号 {task.get('provider_task_id')}"
        return "-"

    def video_task_summary(self, task: dict[str, Any]) -> str:
        lines = [
            f"任务ID：{task.get('id') or '-'}",
            f"状态：{task.get('status') or '-'}",
            f"模型任务号：{task.get('provider_task_id') or '-'}",
            self.video_usage_text(task),
        ]
        storage = self.video_storage_text(task)
        if storage:
            lines.append("视频：已生成，可预览/下载")
        if task.get("error_message"):
            lines.append(f"错误：{task.get('error_message')}")
        return "\n".join(lines)

    def video_usage_text(self, task: dict[str, Any], compact: bool = False) -> str:
        total_tokens = int(task.get("usage_total_tokens") or 0)
        prompt_tokens = int(task.get("usage_prompt_tokens") or 0)
        completion_tokens = int(task.get("usage_completion_tokens") or 0)
        cost = float(task.get("usage_cost_cny") or 0)
        note = str(task.get("usage_note") or "")
        if total_tokens <= 0:
            return "API 未返回 token" if compact else f"消耗：API 未返回 token。{note}".strip()
        if cost > 0:
            cost_text = f"¥{cost:.4f}" if cost < 0.01 else f"¥{cost:.2f}"
        else:
            cost_text = "费用待账单确认"
        if compact:
            return f"{total_tokens} token / {cost_text}"
        detail = f"消耗：{total_tokens} token（输入 {prompt_tokens}，输出 {completion_tokens}），费用 {cost_text}"
        if note:
            detail = f"{detail}。{note}"
        return detail

    def preview_task_video(self, task: dict[str, Any]) -> None:
        url = str(task.get("video_url") or task.get("local_video_url") or task.get("result_video_url") or "")
        storage = self.video_storage_text(task)
        if hasattr(self, "video_usage_label"):
            self.video_usage_label.setText(self.video_usage_text(task))
        self.preview_video_url(url, storage)

    def preview_video_url(self, url: str, storage: str = "") -> None:
        if not hasattr(self, "video_player"):
            return
        self.current_video_url = url or ""
        self.current_video_storage = storage or self.current_video_url
        if self.current_video_storage:
            storage_text = self.current_video_storage if self.current_video_storage.startswith(("C:", "D:", "/", "\\")) else "已生成，可点击下载视频保存到本地"
        else:
            storage_text = "-"
        self.video_storage_label.setText(f"存放位置：{storage_text}")
        if not self.current_video_url:
            self.video_player.stop()
            self.video_preview_status.setText("生成完成后会在这里播放 9:16 视频。")
            return
        self.video_preview_status.setText("视频已生成，可预览或下载。")
        self.video_player.setSource(QUrl(self.current_video_url))
        self.video_player.play()

    def preview_selected_task(self) -> None:
        if not self.current_project:
            return
        row = self.task_table.currentRow()
        if row < 0:
            return
        task_id_item = self.task_table.item(row, 0)
        if not task_id_item:
            return
        task_id = int(task_id_item.text() or 0)
        for task in self.current_project.get("tasks") or []:
            if int(task.get("id") or 0) == task_id:
                self.preview_task_video(task)
                self.video_result.setPlainText(self.video_task_summary(task))
                return

    def open_current_video(self) -> None:
        if not self.current_video_url:
            QMessageBox.information(self, "提示", "当前还没有可打开的视频链接。")
            return
        QDesktopServices.openUrl(QUrl(self.current_video_url))

    def download_current_video(self) -> None:
        if not self.current_video_url:
            QMessageBox.information(self, "提示", "当前还没有可下载的视频链接。")
            return
        default_name = f"video_{int(time.time())}.mp4"
        downloads = Path.home() / "Downloads"
        target, _ = QFileDialog.getSaveFileName(self, "保存视频", str(downloads / default_name), "Video (*.mp4);;All Files (*)")
        if not target:
            return
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(self.current_video_url, timeout=300)
            response.raise_for_status()
            Path(target).write_bytes(response.content)
            self.current_video_storage = target
            self.video_storage_label.setText(f"存放位置：{target}")
            QMessageBox.information(self, "下载完成", f"视频已保存到：{target}")
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))


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
                key_text = "已配置" if item.get("has_access_key") or item.get("access_key_encrypted") else "-"
                rows.append([item.get("config_name"), item.get("service_type"), item.get("api_base_url"), key_text, item.get("status")])
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
            ("service_type", "服务类型", "volcengine_ark/fastmoss/1688_api/custom_api/oxylabs/miaoshou/volcengine-mediakit"),
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
        try:
            self.items = self.gateway.attributes()
        except ApiError as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
            self.items = []
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
        self.chat_input.setPlaceholderText("帮我找适合日本市场的电动工具")
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


def wait_for_auto_publish_result(gateway: DataGateway, task_id: str, poll_seconds: float = 1.5) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(20):
        try:
            latest = gateway.start_auto_publish_task_async(task_id)
            break
        except ApiError as exc:
            if "task not found" not in str(exc).lower() and "任务不存在" not in str(exc):
                raise
            time.sleep(poll_seconds)
    if not latest:
        raise ApiError("任务状态暂时同步失败：后台可能仍在运行，请先等待或点击刷新，不要重复提交。")
    terminal_statuses = {
        "imported",
        "import_failed",
        "image_failed",
        "failed",
        "batch_failed",
        "batch_partial_failed",
    }
    while True:
        progress = latest.get("progress") if isinstance(latest.get("progress"), dict) else {}
        status = str(latest.get("status") or "")
        if status in terminal_statuses or str(progress.get("stage") or "") == "done":
            return latest
        time.sleep(poll_seconds)
        try:
            latest = gateway.get_auto_publish_task(task_id)
        except ApiError as exc:
            if "task not found" not in str(exc).lower() and "任务不存在" not in str(exc):
                raise
            try:
                fallback = gateway.latest_auto_publish_result()
                if fallback.get("task_id") == task_id:
                    latest = fallback
            except ApiError:
                pass
            continue


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
            result = wait_for_auto_publish_result(self.gateway, str(task["task_id"]))
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class AutoPublishBatchTask(QRunnable):
    def __init__(self, gateway: DataGateway, payloads: list[dict[str, Any]], signals: AutoPublishSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.payloads = payloads
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            first_payload = self.payloads[0]
            task = self.gateway.create_1688_batch_auto_publish_task(
                {
                    "offer_urls": [str(payload.get("offer_url") or "") for payload in self.payloads],
                    "publish_count": len(self.payloads),
                    "target_channel": first_payload.get("target_channel") or "TikTok Shop Japan",
                    "target_language": first_payload.get("target_language") or "ja",
                    "erp_url": first_payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270",
                    "dry_run": bool(first_payload.get("dry_run")),
                    "miaoshou_username": first_payload.get("miaoshou_username") or "",
                    "miaoshou_password": first_payload.get("miaoshou_password") or "",
                }
            )
            self.signals.created.emit(task)
            result = wait_for_auto_publish_result(self.gateway, str(task["task_id"]))
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

        self.offer_url_input = QTextEdit()
        self.offer_url_input.setPlaceholderText(
            "支持输入 1688 商品链接，多个链接请换行；\n"
            "例如：https://detail.1688.com/offer/123.html?goods_id=123\n"
            "也可以整行粘贴带标题的文本，系统会自动提取其中的 1688 链接。"
        )
        self.offer_url_input.setMinimumHeight(120)
        self.erp_input = QLineEdit("https://erp.91miaoshou.com/?ac=1og270")
        self.miaoshou_user_input = QLineEdit()
        self.miaoshou_user_input.setPlaceholderText("必填：妙手手机号 / 子账号 / 邮箱")
        self.miaoshou_password_input = QLineEdit()
        self.miaoshou_password_input.setPlaceholderText("必填：妙手密码，验证码在妙手窗口手动输入")
        self.miaoshou_password_input.setEchoMode(QLineEdit.Password)
        self.language_select = QComboBox()
        self.language_select.addItem("日语", "ja")
        self.language_select.addItem("英语", "en")
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
        controls_layout.addWidget(QLabel("目标语言"), 3, 0)
        controls_layout.addWidget(self.language_select, 3, 1)
        controls_layout.addWidget(self.dry_run, 3, 2, 1, 2)
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

        usage_card = QFrame()
        usage_card.setObjectName("Card")
        usage_layout = QVBoxLayout(usage_card)
        usage_layout.setContentsMargins(16, 12, 16, 12)
        usage_layout.setSpacing(6)
        usage_title = QLabel("API 用量统计")
        usage_title.setObjectName("CardTitle")
        self.api_usage_summary = QLabel("等待任务完成后显示调用次数、图片数量和 Token 用量。")
        self.api_usage_summary.setObjectName("Muted")
        self.api_usage_summary.setWordWrap(True)
        self.api_usage_detail = QLabel("暂无数据")
        self.api_usage_detail.setObjectName("ProductMuted")
        self.api_usage_detail.setWordWrap(True)
        usage_layout.addWidget(usage_title)
        usage_layout.addWidget(self.api_usage_summary)
        usage_layout.addWidget(self.api_usage_detail)
        self.layout.addWidget(usage_card)

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
        self.current_task = None
        self.progress_timer.stop()
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
        offer_urls = self.extract_offer_urls(self.offer_url_input.toPlainText())
        if not offer_urls:
            QMessageBox.information(self, "请输入链接", "请先粘贴 1688 商品链接。")
            return
        miaoshou_username = self.miaoshou_user_input.text().strip()
        miaoshou_password = self.miaoshou_password_input.text().strip()
        if not miaoshou_username or not miaoshou_password:
            QMessageBox.information(self, "请填写妙手账号", "请填写本次使用的妙手账号和密码；验证码会在妙手窗口手动完成。")
            return
        payloads = [
            {
                "offer_url": offer_url,
                "publish_count": 1,
                "target_channel": "TikTok Shop Japan",
                "target_language": self.language_select.currentData() or "ja",
                "erp_url": self.erp_input.text().strip() or "https://erp.91miaoshou.com/?ac=1og270",
                "dry_run": self.dry_run.isChecked(),
                "miaoshou_username": miaoshou_username,
                "miaoshou_password": miaoshou_password,
            }
            for offer_url in offer_urls
        ]
        if len(payloads) == 1:
            self.start_background_task(payloads[0])
        else:
            self.start_batch_background_task(payloads)

    def extract_offer_urls(self, text: str) -> list[str]:
        urls: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            matches = re.findall(r"https?://detail\.1688\.com/offer/\d+\.html(?:\?[^\s|$，,；;]*)?", line, flags=re.IGNORECASE)
            if matches:
                urls.extend(matches)
            elif re.fullmatch(r"\d{8,}", line):
                urls.append(f"https://detail.1688.com/offer/{line}.html")
        result: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    def start_background_task(self, payload: dict[str, Any]) -> None:
        self.create_button.setEnabled(False)
        self.create_button.setText("处理中...")
        self.progress_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在创建任务")
        self.reset_api_usage_panel("任务已开始，正在等待 API 用量回传。")
        self.result.setPlainText(
            "任务已开始，正在后台执行。\n\n"
            "这一步会调用 Oxylabs、豆包文案模型、AI MediaKit 图片清理/翻译、模板生成和妙手导入。\n"
            "如果弹出妙手浏览器，请在 10 分钟内手动输入验证码并登录。"
        )
        self.task_signals = AutoPublishSignals()
        self.task_signals.created.connect(self.on_task_created)
        self.task_signals.finished.connect(self.on_task_finished)
        self.task_signals.failed.connect(self.on_task_failed)
        IMAGE_THREAD_POOL.start(AutoPublishTask(self.gateway, payload, self.task_signals))

    def start_batch_background_task(self, payloads: list[dict[str, Any]]) -> None:
        self.create_button.setEnabled(False)
        self.create_button.setText("批量处理中...")
        self.progress_timer.stop()
        self.current_task = None
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"批量任务已开始：{len(payloads)} 个链接")
        self.reset_api_usage_panel(f"批量任务已开始：{len(payloads)} 个链接，正在等待 API 用量回传。")
        self.result.setPlainText(
            f"批量任务已开始，共 {len(payloads)} 个链接。\n\n"
            "多个商品会写入同一个妙手模板，通过产品主编号区分；妙手图片上传和模板导入会自动排队串行执行。"
        )
        self.task_signals = AutoPublishSignals()
        self.task_signals.created.connect(self.on_task_created)
        self.task_signals.finished.connect(self.on_task_finished)
        self.task_signals.failed.connect(self.on_task_failed)
        IMAGE_THREAD_POOL.start(AutoPublishBatchTask(self.gateway, payloads, self.task_signals))

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
        except ApiError as exc:
            if self.gateway.is_invalid_token_error(exc):
                parent = self.window()
                if hasattr(parent, "clear_invalid_session"):
                    parent.clear_invalid_session()
                self.progress_timer.stop()
                self.progress_label.setText("登录已失效，请重新登录")
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
        self.update_api_usage_panel(result)

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
        if self.gateway.is_invalid_token_error(ApiError(message)):
            parent = self.window()
            if hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
            QMessageBox.warning(self, "登录已失效", "登录已失效，请重新登录后再上架。")
            return
        QMessageBox.warning(self, "上架失败", message)

    def reset_flow(self) -> None:
        self.progress_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("待开始")
        self.reset_api_usage_panel()

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
        if isinstance(result.get("batch_results"), list):
            self.render_batch_result(result)
            return
        self.update_api_usage_panel(result)
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
        product_infos = result.get("product_infos") or []
        if len(product_infos) > 1:
            lines.append("")
            lines.append("商品：")
            for index, product in enumerate(product_infos, start=1):
                title = str(product.get("optimized_title") or product.get("title") or product.get("offer_url") or "-")
                offer_id = str(product.get("offer_id") or "-")
                sku_count = len(product.get("optimized_skus") or product.get("skus") or [])
                lines.append(f"- {index}. {title}（货源ID：{offer_id}，SKU：{sku_count} 个）")
        if result.get("template_path"):
            lines.append("")
            lines.append(f"模板文件：{result.get('template_path')}")
        self.append_api_usage_lines(lines, result)
        import_result = result.get("import_result") or {}
        screenshots = import_result.get("screenshots") or []
        if screenshots:
            lines.append("")
            lines.append("失败截图：")
            lines.extend([f"- {path}" for path in screenshots])
        self.result.setPlainText("\n".join(lines))

    def render_batch_result(self, result: dict[str, Any]) -> None:
        batch_results = [item for item in result.get("batch_results", []) if isinstance(item, dict)]
        ok_count = sum(1 for item in batch_results if item.get("ok"))
        failed_count = len(batch_results) - ok_count
        self.update_api_usage_panel(result)
        lines = [
            f"状态：{result.get('status', '-')}",
            f"消息：{result.get('message', '-')}",
            "",
            f"汇总：成功 {ok_count} 个，失败 {failed_count} 个。",
            "",
            "明细：",
        ]
        for index, item in enumerate(batch_results, start=1):
            product = (item.get("product_infos") or [{}])[0] if isinstance(item.get("product_infos"), list) else {}
            title = product.get("optimized_title") or product.get("title") or item.get("offer_url") or "-"
            lines.append(f"{index}. {title}")
            lines.append(f"   状态：{item.get('status', '-')}")
            lines.append(f"   消息：{item.get('message', '-')}")
            if item.get("template_path"):
                lines.append(f"   模板：{item.get('template_path')}")
            errors = item.get("errors") or []
            if errors:
                lines.append("   错误：")
                lines.extend([f"   - {error}" for error in errors[:8]])
            lines.append("")
        self.append_api_usage_lines(lines, result)
        self.result.setPlainText("\n".join(lines).strip())

    def reset_api_usage_panel(self, message: str | None = None) -> None:
        self.api_usage_summary.setText(message or "等待任务完成后显示调用次数、图片数量、Token 用量和预估费用。")
        self.api_usage_detail.setText("暂无数据")

    @staticmethod
    def format_cost_cny(value: Any) -> str:
        cost = float(value or 0)
        if cost <= 0:
            return "¥0"
        if cost < 0.01:
            return f"¥{cost:.4f}"
        return f"¥{cost:.2f}"

    def update_api_usage_panel(self, result: dict[str, Any]) -> None:
        usage = result.get("api_usage") if isinstance(result.get("api_usage"), dict) else {}
        totals = usage.get("totals") if isinstance(usage.get("totals"), dict) else {}
        if not totals:
            return
        request_count = int(totals.get("request_count") or 0)
        image_count = int(totals.get("image_count") or 0)
        total_tokens = int(totals.get("total_tokens") or 0)
        prompt_tokens = int(totals.get("prompt_tokens") or 0)
        completion_tokens = int(totals.get("completion_tokens") or 0)
        success_count = int(totals.get("success_count") or 0)
        failure_count = int(totals.get("failure_count") or 0)
        estimated_cost = self.format_cost_cny(totals.get("estimated_cost_cny"))
        self.api_usage_summary.setText(
            f"总计：请求 {request_count} 次，图片 {image_count} 张，Token {total_tokens} "
            f"（输入 {prompt_tokens}，输出 {completion_tokens}），预估费用 {estimated_cost}，"
            f"成功 {success_count}，失败 {failure_count}"
        )
        by_key = usage.get("by_key") if isinstance(usage.get("by_key"), dict) else {}
        by_provider = usage.get("by_provider") if isinstance(usage.get("by_provider"), dict) else {}
        detail_lines: list[str] = []
        detail_source = by_key if by_key else by_provider
        for name, bucket in sorted(detail_source.items()):
            if not isinstance(bucket, dict):
                continue
            if name == "unknown":
                continue
            detail_lines.append(
                f"{name}：请求 {int(bucket.get('request_count') or 0)} 次，"
                f"图片 {int(bucket.get('image_count') or 0)} 张，"
                f"Token {int(bucket.get('total_tokens') or 0)}，"
                f"费用 {self.format_cost_cny(bucket.get('estimated_cost_cny'))}，"
                f"成功 {int(bucket.get('success_count') or 0)}，失败 {int(bucket.get('failure_count') or 0)}"
            )
        self.api_usage_detail.setText("；".join(detail_lines) if detail_lines else "暂无分 Key 统计")

    def append_api_usage_lines(self, lines: list[str], result: dict[str, Any]) -> None:
        usage = result.get("api_usage") if isinstance(result.get("api_usage"), dict) else {}
        totals = usage.get("totals") if isinstance(usage.get("totals"), dict) else {}
        if not totals:
            return
        lines.append("")
        lines.append("API 用量：")
        lines.append(
            "总计："
            f"请求 {int(totals.get('request_count') or 0)} 次，"
            f"图片 {int(totals.get('image_count') or 0)} 张，"
            f"Token {int(totals.get('total_tokens') or 0)} "
            f"（输入 {int(totals.get('prompt_tokens') or 0)}，输出 {int(totals.get('completion_tokens') or 0)}），"
            f"预估费用 {self.format_cost_cny(totals.get('estimated_cost_cny'))}"
        )
        by_provider = usage.get("by_provider") if isinstance(usage.get("by_provider"), dict) else {}
        if by_provider:
            lines.append("按服务：")
            for name, bucket in sorted(by_provider.items()):
                if not isinstance(bucket, dict):
                    continue
                lines.append(
                    f"- {name}：请求 {int(bucket.get('request_count') or 0)} 次，"
                    f"图片 {int(bucket.get('image_count') or 0)} 张，"
                    f"Token {int(bucket.get('total_tokens') or 0)}，"
                    f"费用 {self.format_cost_cny(bucket.get('estimated_cost_cny'))}，"
                    f"成功 {int(bucket.get('success_count') or 0)}，失败 {int(bucket.get('failure_count') or 0)}"
                )
        by_key = usage.get("by_key") if isinstance(usage.get("by_key"), dict) else {}
        if by_key:
            lines.append("按 Key：")
            for name, bucket in sorted(by_key.items()):
                if not isinstance(bucket, dict) or name == "unknown":
                    continue
                lines.append(
                    f"- {name}：请求 {int(bucket.get('request_count') or 0)} 次，"
                    f"图片 {int(bucket.get('image_count') or 0)} 张，"
                    f"Token {int(bucket.get('total_tokens') or 0)}，"
                    f"费用 {self.format_cost_cny(bucket.get('estimated_cost_cny'))}，"
                    f"成功 {int(bucket.get('success_count') or 0)}，失败 {int(bucket.get('failure_count') or 0)}"
                )
        by_purpose = usage.get("by_purpose") if isinstance(usage.get("by_purpose"), dict) else {}
        if by_purpose:
            lines.append("按用途：")
            for name, bucket in sorted(by_purpose.items()):
                if not isinstance(bucket, dict):
                    continue
                lines.append(
                    f"- {name}：请求 {int(bucket.get('request_count') or 0)} 次，"
                    f"图片 {int(bucket.get('image_count') or 0)} 张，"
                    f"Token {int(bucket.get('total_tokens') or 0)}，"
                    f"费用 {self.format_cost_cny(bucket.get('estimated_cost_cny'))}，"
                    f"成功 {int(bucket.get('success_count') or 0)}，失败 {int(bucket.get('failure_count') or 0)}"
                )
        by_model = usage.get("by_model") if isinstance(usage.get("by_model"), dict) else {}
        if by_model:
            lines.append("按模型/API：")
            for name, bucket in sorted(by_model.items()):
                if not isinstance(bucket, dict):
                    continue
                lines.append(
                    f"- {name}：请求 {int(bucket.get('request_count') or 0)} 次，"
                    f"图片 {int(bucket.get('image_count') or 0)} 张，"
                    f"Token {int(bucket.get('total_tokens') or 0)}，"
                    f"费用 {self.format_cost_cny(bucket.get('estimated_cost_cny'))}，"
                    f"成功 {int(bucket.get('success_count') or 0)}，失败 {int(bucket.get('failure_count') or 0)}"
                )


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
            background: transparent; color: $text; font-size: 20px; font-weight: 900;
        }
        #BrandSub {
            background: transparent; color: $muted; font-size: 11px; letter-spacing: 0px;
        }
        #SideNav {
            background: $sidebar; color: $muted; border: 0; padding: 14px;
            outline: 0; font-size: 15px;
        }
        #SideNav::item { height: 48px; border-radius: 10px; margin: 5px; padding-left: 14px; }
        #SideNav::item:hover { background: $panel2; color: $text; }
        #SideNav::item:selected { background: $accent; color: #ffffff; }
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
