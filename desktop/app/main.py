from __future__ import annotations

import sys
import json
import re
import time
import math
import base64
import hashlib
import hmac
import mimetypes
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import date, datetime
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QDate, QEvent, QObject, QPointF, QRunnable, QRectF, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
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
    QProgressDialog,
    QDoubleSpinBox,
    QDateEdit,
    QFileDialog,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from api.client import ApiClient, ApiError


CURRENT_APP_VERSION = "1.0.0"


if getattr(sys, "frozen", False):
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "app"
else:
    APP_DIR = Path(__file__).resolve().parent
ICON_DIR = APP_DIR / "assets" / "icons"
DESKTOP_BROWSER_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
MENU_ICON_MAP = {
    "智能选品": "menu_ai.svg",
    "选品库": "menu_library.svg",
    "新品榜单": "menu_new.svg",
    "采集箱": "menu_favorite.svg",
    "视频生成": "menu_course.svg",
    "店铺管理": "menu_store.svg",
    "数据看板": "menu_dashboard.svg",
    "个人中心": "menu_settings.svg",
    "设置": "menu_settings.svg",
    "教师看板": "menu_teacher.svg",
    "任务看板": "menu_tasks.svg",
    "用户管理": "menu_users.svg",
    "模型配置": "menu_model.svg",
    "第三方 API": "menu_api.svg",
    "选品属性": "menu_attributes.svg",
    "版本更新": "menu_settings.svg",
}

MENU_ROLE_ACCESS = {
    "admin": None,
    "teacher": {
        "数据看板", "个人中心", "关于益行", "教师看板", "选品属性", "新品榜单", "智能选品", "视频生成",
    },
    "student": {
        "智能选品", "选品库", "新品榜单", "采集箱", "店铺管理", "关于益行", "个人中心", "视频生成",
    },
}


def icon_path(filename: str) -> str:
    return str(ICON_DIR / filename)


def load_icon(filename: str) -> QIcon:
    path = icon_path(filename)
    if not filename.lower().endswith(".svg"):
        return QIcon(path)
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QIcon(path)
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def open_external_url(url: str, parent: QWidget | None = None) -> None:
    """Use the system browser explicitly instead of relying on QLabel defaults."""
    target = str(url or "").strip()
    parsed = QUrl(target)
    if parsed.scheme().lower() not in {"http", "https"} or not parsed.host():
        QMessageBox.information(parent, "链接不可用", "该商品没有有效的 1688 商品链接。")
        return
    if sys.platform.startswith("win"):
        try:
            os.startfile(target)
            return
        except OSError:
            pass
    if QDesktopServices.openUrl(parsed):
        return
    QMessageBox.warning(parent, "打开失败", "系统浏览器无法打开该 1688 链接。")


def external_link_button(text: str, url: str, parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("CollectionLink")
    button.setFlat(True)
    button.setMinimumHeight(0)
    link_font = button.font()
    link_font.setUnderline(True)
    button.setFont(link_font)
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(lambda checked=False, target=url: open_external_url(target, parent))
    return button


def show_error_details(parent: QWidget, title: str, error: Exception | str) -> None:
    """Show long runtime errors in a selectable, scrollable window."""
    if isinstance(error, Exception):
        message = str(error).strip()
        if not message:
            message = f"{type(error).__name__}: {error!r}"
    else:
        message = str(error).strip() or "未提供错误详情"
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(760, 420)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    hint = QLabel("错误详情（可滚动查看和复制）")
    hint.setObjectName("DialogTitle")
    layout.addWidget(hint)
    detail = QTextEdit()
    detail.setReadOnly(True)
    detail.setPlainText(message)
    detail.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    layout.addWidget(detail, 1)
    close_button = QPushButton("关闭")
    close_button.clicked.connect(dialog.accept)
    actions = QHBoxLayout()
    actions.addStretch()
    actions.addWidget(close_button)
    layout.addLayout(actions)
    dialog.exec()


def show_credit_recharge_prompt(parent: QWidget) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle("积分不足")
    box.setText("本次操作需要消耗 10 积分，当前积分不足。")
    box.setInformativeText("请先前往个人中心充值积分。")
    recharge = box.addButton("前往个人中心", QMessageBox.AcceptRole)
    box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is recharge:
        window = parent.window()
        if isinstance(parent, QDialog) and parent is not window:
            parent.close()
        nav = getattr(window, "nav", None)
        if nav is None:
            return
        for index in range(nav.count()):
            item = nav.item(index)
            if item and item.text() == "个人中心":
                nav.setCurrentRow(index)
                return


def enable_label_selection(label: QLabel) -> None:
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)


class TextSelectionFilter(QObject):
    """Make displayed QLabel text selectable without changing button/input behavior."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.ChildAdded:
            child = event.child()
            if isinstance(child, QLabel):
                enable_label_selection(child)
        return super().eventFilter(watched, event)


class CenteredNavDelegate(QStyledItemDelegate):
    """Paint each navigation icon and label as one centered group."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if not index.flags() & Qt.ItemIsEnabled:
            return
        painter.save()
        rect = option.rect.adjusted(2, 1, -2, -1)
        if option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(21, 152, 120, 38))
            painter.drawRoundedRect(rect, 8, 8)
        elif option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(option.palette.alternateBase())
            painter.drawRoundedRect(rect, 8, 8)

        text = str(index.data(Qt.DisplayRole) or "")
        icon = index.data(Qt.DecorationRole)
        font = index.data(Qt.FontRole) or option.font
        painter.setFont(font)
        text_width = QFontMetrics(font).horizontalAdvance(text)
        icon_size = option.decorationSize
        gap = 8 if text and icon and not icon.isNull() else 0
        total_width = (icon_size.width() if icon and not icon.isNull() else 0) + gap + text_width
        start_x = rect.left() + 28
        if icon and not icon.isNull():
            icon.paint(painter, QRectF(start_x, rect.center().y() - icon_size.height() / 2, icon_size.width(), icon_size.height()).toRect())
            start_x += icon_size.width() + gap
        painter.setPen(QColor("#17846e") if option.state & QStyle.State_Selected else option.palette.text().color())
        painter.drawText(QRectF(start_x, rect.top(), text_width, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class PromptEditorFrame(QFrame):
    """Multiline prompt editor with embedded counter and analyze action."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StudioPromptFrame")
        self.editor = QTextEdit(self)
        self.editor.setObjectName("StudioPromptEditor")
        self.editor.setPlaceholderText(
            "✦  告诉我您想找什么样的产品?\n例如：最近在日本TikTok上热卖的厨房小工具，价格在1000日元以内"
        )
        self.editor.setAcceptRichText(False)
        self.editor.setFrameStyle(QFrame.NoFrame)
        self.count_label = QLabel("0/300", self)
        self.count_label.setObjectName("StudioPromptCount")
        self.analyze_button = QPushButton("智能选品", self)
        self.analyze_button.setObjectName("StudioAnalyze")
        self.analyze_button.setFixedSize(96, 38)
        self.credit_label = QLabel("10积分", self)
        self.credit_label.setObjectName("CreditHint")
        self.credit_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def set_credit_cost(self, cost: int) -> None:
        self.credit_label.setText(f"{int(cost)}积分")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        margin = 10
        button_width = self.analyze_button.width()
        self.credit_label.adjustSize()
        self.analyze_button.move(self.width() - button_width - margin, self.height() - self.analyze_button.height() - margin)
        self.count_label.adjustSize()
        self.count_label.move(self.analyze_button.x() - self.count_label.width() - 14, self.height() - self.count_label.height() - 21)
        self.credit_label.move(
            self.analyze_button.x() + self.analyze_button.width() - self.credit_label.width(),
            self.analyze_button.y() - self.credit_label.height() - 2,
        )



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

    def app_version(self) -> dict[str, Any]:
        return self.client.get("/api/app/version", timeout=10)

    def app_releases(self) -> list[dict[str, Any]]:
        return self.client.get("/api/admin/app-releases")

    def upload_app_release(self, file_path: str, version: str, release_notes: str, force_update: bool) -> dict[str, Any]:
        return self.client.upload(
            "/api/admin/app-releases/upload",
            file_path,
            "package",
            {"version": version, "release_notes": release_notes, "force_update": "1" if force_update else "0"},
            timeout=1800,
        )

    def publish_app_release(self, release_id: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/app-releases/{release_id}/publish")

    def delete_app_release(self, release_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/app-releases/{release_id}")

    def is_invalid_token_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "请重新登录" in str(exc) or "invalid token" in text or "not authenticated" in text or "could not validate credentials" in text

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.client.login(username, password)
        self.user = data["user"]
        self.save_session()
        return self.user

    def register(self, username: str, password: str, real_name: str = "") -> dict[str, Any]:
        data = self.client.post("/api/auth/register", {"username": username, "password": password, "real_name": real_name})
        self.user = data["user"]
        self.client.token = data.get("access_token")
        self.save_session()
        return self.user

    def send_phone_code(self, phone: str) -> dict[str, Any]:
        return self.client.post("/api/auth/sms/send", {"phone": phone})

    def phone_login(self, phone: str, code: str) -> dict[str, Any]:
        data = self.client.post("/api/auth/sms/login", {"phone": phone, "code": code})
        self.user = data["user"]
        self.client.token = data.get("access_token")
        self.save_session()
        return self.user

    def hot_products(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/products/hot")

    def daily_recommendations(self, region: str = "JP", list_type: str = "new", category: str = "全部", start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get(f"/api/daily-recommendations?region={region}&list_type={list_type}&category={category}&start_date={start_date}&end_date={end_date}")

    def favorites(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/favorites")

    def create_favorite(self, item: dict[str, Any]) -> dict[str, Any]:
        snapshot = {key: value for key, value in item.items() if key not in {"id", "source_product_id", "derived_id", "recommendation_id", "product_id"}}
        source_type = str(item.get("source_type") or "").lower()
        if source_type not in {"derived", "new_product", "ai_search"}:
            source_type = "ai_search" if item.get("search_query") else ("new_product" if item.get("list_type") else "derived")
        return self.client.post(
            "/api/favorites",
            {
                "source_type": source_type,
                "title": item.get("title") or item.get("derived_title") or "",
                "image_url": item.get("image_url") or item.get("supplier_image_url") or "",
                "price": item.get("price") or item.get("supplier_price") or item.get("suggested_price_min") or 0,
                "currency": item.get("currency") or "JPY",
                "sales_count": int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0)),
                "category": item.get("category") or "",
                "recommendation_reason": item.get("recommendation_reason") or item.get("reason_summary") or "",
                "analysis_report": item.get("analysis_report") or {},
                "product_snapshot": snapshot,
            },
        )

    def delete_favorite(self, favorite_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/favorites/{favorite_id}")

    def derived_products(self, product_id: int) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get(f"/api/teacher/products/{product_id}/derived-products")

    def recommended_derived_products(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.user:
            return []
        size = int(limit or 12)
        return self.client.get(f"/api/derived-recommendations?limit={size}")

    def selection_library_products(self, limit: int = 100) -> list[dict[str, Any]]:
        """Load the latest derived products for the personal selection library."""
        return self.recommended_derived_products(limit)

    def generate_derived_products(self, product_id: int) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "message": "请先登录后端账号"}
        return self.client.post(f"/api/ai/products/{product_id}/generate-derived")

    def start_product_full_pipeline(self, product_id: int) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "message": "请先登录后端账号"}
        return self.client.post(f"/api/ai/products/{product_id}/generate-full-task")

    def product_full_pipeline_task(self, task_id: int) -> dict[str, Any]:
        return self.client.get(f"/api/ai/product-full-tasks/{task_id}")

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

    def change_password(self, old_password: str, new_password: str) -> dict[str, Any]:
        return self.client.post("/api/auth/change-password", {"old_password": old_password, "new_password": new_password})

    def model_configs(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/model-configs")

    def test_model(self, model_config_id: int, text: str, image_url: str = "") -> dict[str, Any]:
        return self.client.post("/api/admin/model-test", {"model_config_id": model_config_id, "text": text, "image_url": image_url}, timeout=480)

    def save_model_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        if config_id:
            return self.client.put(f"/api/admin/model-configs/{config_id}", payload)
        return self.client.post("/api/admin/model-configs", payload)

    def set_model_status(self, config_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/model-configs/{config_id}/status", {"status": status})

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

    def sync_fastmoss_products(self, region: str = "JP", list_type: str = "new") -> dict[str, Any]:
        return self.client.post(f"/api/fastmoss/sync-products?page=1&region={region}&list_type={list_type}")

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

    def miaoshou_shop_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/auto-publish/miaoshou/shop-list", payload, timeout=60)

    def reauthorize_miaoshou_picture_space(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.client.post("/api/auto-publish/miaoshou/reauthorize-picture-space", payload, timeout=600)

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

    def system_settings(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/system-settings")

    def update_system_settings(self, values: dict[str, str]) -> list[dict[str, Any]]:
        return self.client.put("/api/admin/system-settings", {"values": values})

    def queue_pending_derivations(self, limit: int | None = None, min_derived_count: int | None = None) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "queued_count": 0, "message": "请先登录后端账号"}
        payload = {key: value for key, value in {"limit": limit, "min_derived_count": min_derived_count}.items() if value is not None}
        return self.client.post("/api/pipeline/derivations/queue", payload)

    def queue_supplier_matches(self, limit: int | None = None, threshold: float | None = None, max_candidates: int | None = None, page_size: int | None = None) -> dict[str, Any]:
        if not self.user:
            return {"ok": False, "queued": False, "message": "请先登录后端账号"}
        return self.client.post(
            "/api/pipeline/suppliers/1688/queue",
            {key: value for key, value in {"limit": limit, "threshold": threshold, "max_candidates": max_candidates, "page_size": page_size}.items() if value is not None},
        )

    def start_ai_selection(self, message: str, count: int = 10) -> dict[str, Any]:
        return self.client.post("/api/ai/chat-selection", {"message": message, "count": count})

    def ai_selection_task(self, task_id: int) -> dict[str, Any]:
        return self.client.get(f"/api/ai/selection-tasks/{task_id}")

    def user_search_results(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/ai/search-results")

    def add_to_selection_library(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.user:
            raise ApiError("请先登录")
        return self.client.post("/api/ai/library-products", {"product": item})

    def save_attribute(self, payload: dict[str, Any], attribute_id: int | None = None) -> dict[str, Any]:
        if attribute_id:
            return self.client.put(f"/api/admin/selection-attributes/{attribute_id}", payload)
        return self.client.post("/api/admin/selection-attributes", payload)

    def set_attribute_status(self, attribute_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/selection-attributes/{attribute_id}/status", {"status": status})

    def delete_attribute(self, attribute_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/selection-attributes/{attribute_id}")

    def prompt_constants(self) -> list[dict[str, Any]]:
        if not self.user:
            return []
        return self.client.get("/api/admin/prompt-constants")

    def save_prompt_constant(self, payload: dict[str, Any], constant_id: int | None = None) -> dict[str, Any]:
        if constant_id:
            return self.client.put(f"/api/admin/prompt-constants/{constant_id}", payload)
        return self.client.post("/api/admin/prompt-constants", payload)

    def set_prompt_constant_status(self, constant_id: int, status: int) -> dict[str, Any]:
        return self.client.patch(f"/api/admin/prompt-constants/{constant_id}/status", {"status": status})

    def delete_prompt_constant(self, constant_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/prompt-constants/{constant_id}")

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
    layout = QHBoxLayout(box)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(8)
    title = QLabel(text)
    title.setObjectName("PageTitle")
    layout.addWidget(title)
    if subtitle:
        separator = QLabel("·")
        separator.setObjectName("Muted")
        layout.addWidget(separator)
        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        layout.addWidget(sub)
    layout.addStretch()
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

DIMENSION_REPORT_ALIASES = {
    "dimension_4": ("短视频种草", "短视频流量种草适配能力"),
    "dimension_5": ("日本偏好", "日本市场偏好"),
    "dimension_6": ("新奇特", "是否属于新奇特商品"),
}


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
            for alias in DIMENSION_REPORT_ALIASES.get(code, (default_name,)):
                row = raw_report.get(alias)
                if row:
                    break
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
        self.setWindowTitle("益行跨境AI平台")
        self.setWindowIcon(QIcon(icon_path("tk_brand.png")))
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


class RegisterDialog(QDialog):
    def __init__(self, gateway: DataGateway, parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.user: dict[str, Any] | None = None
        self.setWindowTitle("注册学生账号")
        self.setWindowIcon(QIcon(icon_path("tk_brand.png")))
        self.resize(420, 330)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel("注册学生账号")
        title.setObjectName("LoginTitle")
        hint = QLabel("注册成功后默认角色为学生，可直接使用智能选品功能。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.real_name = QLineEdit()
        self.real_name.setPlaceholderText("姓名或昵称（可选）")
        self.username = QLineEdit()
        self.username.setPlaceholderText("登录账号")
        self.password = QLineEdit()
        self.password.setPlaceholderText("登录密码（至少 6 位）")
        self.password.setEchoMode(QLineEdit.Password)
        self.confirm = QLineEdit()
        self.confirm.setPlaceholderText("确认密码")
        self.confirm.setEchoMode(QLineEdit.Password)
        actions = QHBoxLayout()
        cancel = QPushButton("取消")
        submit = QPushButton("注册并登录")
        cancel.clicked.connect(self.reject)
        submit.clicked.connect(self.do_register)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(submit)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addWidget(self.real_name)
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addWidget(self.confirm)
        layout.addLayout(actions)

    def do_register(self) -> None:
        if self.password.text() != self.confirm.text():
            QMessageBox.information(self, "提示", "两次输入的密码不一致。")
            return
        try:
            self.user = self.gateway.register(self.username.text().strip(), self.password.text(), self.real_name.text().strip())
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "注册失败", str(exc))


class LoginDialog(QDialog):
    def __init__(self, gateway: DataGateway, parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.user: dict[str, Any] | None = None
        self.setWindowTitle("用户登录")
        self.setWindowIcon(QIcon(icon_path("tk_brand.png")))
        self.resize(440, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel("微信登录")
        title.setObjectName("LoginTitle")
        hint = QLabel("微信扫码登录，首次登录将自动创建学生账号")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        self.mode_tabs = QHBoxLayout()
        self.wechat_tab = QPushButton("微信扫码登录")
        self.phone_tab = QPushButton("手机号登录")
        self.account_tab = QPushButton("账号密码登录")
        for button in (self.wechat_tab, self.phone_tab, self.account_tab):
            button.setObjectName("LoginModeTab")
            self.mode_tabs.addWidget(button, 1)
        self.wechat_tab.clicked.connect(lambda: self.mode_stack.setCurrentIndex(0))
        self.phone_tab.clicked.connect(lambda: self.mode_stack.setCurrentIndex(1))
        self.account_tab.clicked.connect(lambda: self.mode_stack.setCurrentIndex(2))
        layout.addLayout(self.mode_tabs)

        self.mode_stack = QStackedWidget()
        wechat_panel = QWidget()
        wechat_layout = QVBoxLayout(wechat_panel)
        wechat_layout.setContentsMargins(0, 14, 0, 8)
        wechat_title = QLabel("微信扫码，关注公众号")
        wechat_title.setAlignment(Qt.AlignCenter)
        wechat_title.setObjectName("LoginQrTitle")
        qr = QLabel("微信登录二维码待配置")
        qr.setAlignment(Qt.AlignCenter)
        qr.setObjectName("LoginQrPlaceholder")
        qr.setMinimumHeight(210)
        wechat_layout.addWidget(wechat_title)
        wechat_layout.addWidget(qr, 1)
        wechat_layout.addWidget(QLabel("配置微信开放平台参数后，扫码会自动登录；首次登录自动创建学生账号。"), 0, Qt.AlignCenter)
        self.mode_stack.addWidget(wechat_panel)

        phone_panel = QWidget()
        phone_layout = QVBoxLayout(phone_panel)
        phone_layout.setContentsMargins(0, 14, 0, 8)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("请输入手机号")
        self.phone_code = QLineEdit()
        self.phone_code.setPlaceholderText("请输入验证码")
        phone_code_row = QHBoxLayout()
        phone_code_row.addWidget(self.phone_code, 1)
        send_code = QPushButton("获取验证码")
        send_code.clicked.connect(self.send_phone_code)
        phone_code_row.addWidget(send_code)
        phone_layout.addWidget(self.phone_input)
        phone_layout.addLayout(phone_code_row)
        phone_login = QPushButton("登录")
        phone_login.clicked.connect(self.do_phone_login)
        phone_layout.addWidget(phone_login)
        self.mode_stack.addWidget(phone_panel)

        account_panel = QWidget()
        account_layout = QVBoxLayout(account_panel)
        account_layout.setContentsMargins(0, 14, 0, 8)
        self.username = QLineEdit()
        self.username.setPlaceholderText("账号")
        self.password = QLineEdit()
        self.password.setPlaceholderText("密码")
        self.password.setEchoMode(QLineEdit.Password)
        account_login = QPushButton("登录")
        account_login.clicked.connect(self.do_login)
        account_layout.addWidget(self.username)
        account_layout.addWidget(self.password)
        account_layout.addWidget(account_login)
        self.mode_stack.addWidget(account_panel)
        layout.addWidget(self.mode_stack, 1)

    def send_phone_code(self) -> None:
        try:
            result = self.gateway.send_phone_code(self.phone_input.text().strip())
            QMessageBox.information(self, "验证码已发送", str(result.get("message") or "请查收短信。"))
        except Exception as exc:
            QMessageBox.warning(self, "发送失败", str(exc))

    def do_phone_login(self) -> None:
        try:
            self.user = self.gateway.phone_login(self.phone_input.text().strip(), self.phone_code.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "登录失败", str(exc))
            return
        self.accept()

    def do_login(self) -> None:
        try:
            self.user = self.gateway.login(self.username.text().strip(), self.password.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "登录失败", f"账号或密码不正确，或后端不可用。\n{exc}")
            return
        self.accept()


class UpdateCheckSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class UpdateCheckTask(QRunnable):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.signals = UpdateCheckSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.gateway.app_version())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class UpdateDownloadSignals(QObject):
    progress = Signal(int)
    finished = Signal(str)
    failed = Signal(str)


class UpdateDownloadTask(QRunnable):
    def __init__(self, url: str, expected_sha256: str = "") -> None:
        super().__init__()
        self.url = url
        self.expected_sha256 = expected_sha256.lower().strip()
        self.signals = UpdateDownloadSignals()

    @Slot()
    def run(self) -> None:
        try:
            import hashlib

            response = requests.get(self.url, stream=True, timeout=(10, 300), headers={"User-Agent": "TKSelectionAssistant-Updater"})
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            digest = hashlib.sha256()
            suffix = Path(self.url.split("?", 1)[0]).suffix or ".exe"
            target = Path(tempfile.gettempdir()) / f"tk-selection-update{suffix}"
            with target.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if total:
                        self.signals.progress.emit(min(99, int(downloaded * 100 / total)))
            if self.expected_sha256 and digest.hexdigest().lower() != self.expected_sha256:
                target.unlink(missing_ok=True)
                raise RuntimeError("更新包校验失败，文件可能已损坏。")
            self.signals.progress.emit(100)
            self.signals.finished.emit(str(target))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, gateway: DataGateway, user: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.gateway = gateway
        if user is None:
            user = self.gateway.user
        self.user = user
        self.setWindowTitle("益行跨境AI平台 - 系统管理员")
        self.setWindowIcon(QIcon(icon_path("tk_brand.png")))
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
        brand_icon.setPixmap(QIcon(icon_path("tk_brand.png")).pixmap(34, 34))
        brand_icon.setFixedSize(30, 30)
        brand = QLabel("TK跨境助手")
        brand.setObjectName("BrandTitle")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand, 1)
        brand_sub = QLabel("TikTok 日本选品专家")
        brand_sub.setObjectName("BrandSub")
        brand_layout.addLayout(brand_row)
        brand_layout.addWidget(brand_sub)

        sidebar.setFixedWidth(260)
        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(260)
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setItemDelegate(CenteredNavDelegate(self.nav))
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
        self.nav.setCurrentRow(0)
        self.update_check_task: UpdateCheckTask | None = None
        self.update_progress: QProgressDialog | None = None
        QTimer.singleShot(1500, self.check_for_updates)

    def add_nav_separator(self) -> None:
        item = QListWidgetItem("")
        item.setFlags(Qt.NoItemFlags)
        item.setSizeHint(QSize(1, 26))
        item.setData(Qt.UserRole, -1)
        self.nav.addItem(item)
        line = QFrame()
        line.setObjectName("SideSeparator")
        line.setFixedHeight(1)
        line.setStyleSheet("background: #e1eaf0;")
        self.nav.setItemWidget(item, line)

    def add_page(self, name: str, page: QWidget, icon: str = "") -> None:
        item = QListWidgetItem(name)
        icon_name = MENU_ICON_MAP.get(name) or icon
        if icon_name:
            item.setIcon(load_icon(icon_name))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFont(QFont("Microsoft YaHei UI", 14, 700))
        item.setData(Qt.UserRole, len(self.pages))
        self.nav.addItem(item)
        self.stack.addWidget(page)
        self.pages.append(page)

    def setup_pages(self) -> None:
        self.add_page("智能选品", SelectionStudioPage(self.gateway), "01_智能选品.ico")
        self.add_page("选品库", SelectionLibraryPage(self.gateway), "08_选品属性.ico")
        self.add_page("新品榜单", NewProductsPage(self.gateway), "01_智能选品.ico")
        self.add_page("采集箱", FavoritesPage(self.gateway), "05_主题皮肤.ico")
        self.add_page("视频生成", VideoGenerationPage(self.gateway), "menu_course.svg")
        self.add_nav_separator()
        self.add_page("店铺管理", AutoPublishPage(self.gateway), "10_TK跨境助手.ico")
        self.add_page("数据看板", DataDashboardPage(self.gateway), "07_第三方API.ico")
        self.add_nav_separator()
        self.add_page("个人中心", PersonalCenterPage(self.gateway, self.apply_theme, self.apply_font), "menu_settings.svg")
        about_page = InfoPage("关于益行", "益行跨境 AI 平台", f"益行跨境 AI 平台专注 TikTok 日本站跨境选品、商品分析、1688 货源匹配和店铺运营。\n\n当前版本：{CURRENT_APP_VERSION}\n服务地址：" + self.gateway.client.base_url)
        about_page.update_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        self.add_page("关于益行", about_page, "menu_settings.svg")
        self.add_nav_separator()
        self.add_page("教师看板", TeacherDashboardPage(self.gateway), "02_教师看板.ico")
        self.add_page("任务看板", PipelinePage(self.gateway), "07_第三方API.ico")
        self.add_page("用户管理", AdminUsersPage(self.gateway), "03_用户管理.ico")
        self.add_page("模型配置", SimpleConfigPage("模型配置", self.gateway.model_configs, ["配置名称", "服务商", "类型", "Base URL", "模型", "Key", "使用中"], self.gateway, "model"), "04_模型配置.ico")
        self.add_page("模型测试", ModelTestPage(self.gateway), "04_模型配置.ico")
        self.add_page("第三方 API", SimpleConfigPage("第三方 API 配置", self.gateway.third_party_configs, ["配置名称", "服务类型", "状态"], self.gateway, "third"), "07_第三方API.ico")
        self.add_page("选品属性", AttributePage(self.gateway), "08_选品属性.ico")
        self.add_page("版本更新", VersionUpdatePage(self.gateway), "menu_settings.svg")

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
            self.login_button.setText("退出登录")
            self.setWindowTitle(f"益行跨境AI平台 - {self.user.get('real_name') or '系统管理员'}")
            self.apply_menu_permissions()
            self.refresh_credit_controls()
            return
        self.user_avatar.setText("未")
        self.user_name.setText("未登录")
        self.user_role.setText("请登录服务器账号")
        self.user_status.setText("登录后连接后端服务")
        self.login_button.setText("登录")
        self.setWindowTitle("益行跨境AI平台")
        self.apply_menu_permissions()
        self.refresh_credit_controls()

    def refresh_credit_controls(self) -> None:
        for page in getattr(self, "pages", []):
            refresh = getattr(page, "refresh_credit_state", None)
            if callable(refresh):
                refresh()

    def apply_menu_permissions(self) -> None:
        """Filter navigation entries by role and keep separator groups tidy."""
        role = str((self.user or {}).get("role") or "student").lower()
        allowed = MENU_ROLE_ACCESS.get(role, MENU_ROLE_ACCESS["student"])
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if not item:
                continue
            page_data = item.data(Qt.UserRole)
            if page_data == -1:
                continue
            item.setHidden(allowed is not None and item.text() not in allowed)

        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if not item or item.data(Qt.UserRole) != -1:
                continue
            previous_visible = any(
                self.nav.item(index) and self.nav.item(index).data(Qt.UserRole) != -1 and not self.nav.item(index).isHidden()
                for index in range(row - 1, -1, -1)
            )
            next_visible = any(
                self.nav.item(index) and self.nav.item(index).data(Qt.UserRole) != -1 and not self.nav.item(index).isHidden()
                for index in range(row + 1, self.nav.count())
            )
            item.setHidden(not (previous_visible and next_visible))

        current = self.nav.currentItem()
        if current and not current.isHidden():
            return
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item and item.data(Qt.UserRole) != -1 and not item.isHidden():
                self.nav.setCurrentRow(row)
                return

    def open_video_generation_page(self) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item and item.text() == "视频生成" and not item.isHidden():
                self.nav.setCurrentRow(row)
                return
        QMessageBox.information(self, "视频生成", "当前没有找到视频生成入口，请先登录或刷新页面。")

    def open_login_dialog(self) -> None:
        if self.user:
            self.gateway.clear_session()
            self.user = None
            self.update_login_status()
            return
        dialog = LoginDialog(self.gateway, self)
        if dialog.exec() == QDialog.Accepted and dialog.user:
            self.user = dialog.user
            self.update_login_status()
            for page in self.pages:
                if hasattr(page, "loaded"):
                    setattr(page, "loaded", False)
            self.on_page_changed(self.nav.currentRow())

    def on_page_changed(self, index: int) -> None:
        item = self.nav.item(index)
        page_data = item.data(Qt.UserRole) if item else None
        page_index = int(page_data) if page_data is not None else -1
        if page_index < 0:
            return
        self.stack.setCurrentIndex(page_index)
        if 0 <= page_index < len(self.pages):
            page = self.pages[page_index]
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
                    show_error_details(self, "加载失败", exc)

    def clear_invalid_session(self) -> None:
        self.gateway.clear_session()
        self.user = None
        self.update_login_status()
        self.user_status.setText("请重新登录")

    def invalidate_product_pages(self) -> None:
        """Make product views reread the server after a FastMoss refresh."""
        for page in self.pages:
            if hasattr(page, "loaded"):
                setattr(page, "loaded", False)
        current = self.stack.currentWidget()
        activate = getattr(current, "activate", None)
        if callable(activate):
            activate()

    def apply_theme(self, theme_name: str) -> None:
        app = QApplication.instance()
        if app:
            apply_style(app, theme_name)

    def apply_font(self, family: str, size: int) -> None:
        app = QApplication.instance()
        if not app:
            return
        app.setFont(QFont(family, int(size)))
        for item_index in range(self.nav.count()):
            item = self.nav.item(item_index)
            if item and item.data(Qt.UserRole) != -1:
                item.setFont(QFont(family, int(size), 500))

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        numbers = [int(item) for item in re.findall(r"\d+", str(value or ""))]
        return tuple(numbers or [0])

    def check_for_updates(self, manual: bool = False) -> None:
        if self.update_check_task is not None:
            return
        task = UpdateCheckTask(self.gateway)
        self.update_check_task = task
        task.signals.finished.connect(lambda manifest: self._on_update_manifest(manifest, manual))
        task.signals.failed.connect(lambda message: self._on_update_check_failed(message, manual))
        QThreadPool.globalInstance().start(task)

    def _on_update_check_failed(self, message: str, manual: bool) -> None:
        self.update_check_task = None
        if manual:
            QMessageBox.warning(self, "检查更新失败", message)

    def _on_update_manifest(self, manifest: object, manual: bool) -> None:
        self.update_check_task = None
        data = manifest if isinstance(manifest, dict) else {}
        latest = str(data.get("version") or CURRENT_APP_VERSION)
        if self._version_tuple(latest) <= self._version_tuple(CURRENT_APP_VERSION):
            if manual:
                QMessageBox.information(self, "检查更新", f"当前已经是最新版本（{CURRENT_APP_VERSION}）。")
            return
        download_url = str(data.get("download_url") or "").strip()
        notes = str(data.get("release_notes") or "暂无更新说明")
        if not download_url:
            QMessageBox.information(self, "发现新版本", f"发现版本 {latest}，但服务器尚未配置安装包下载地址。\n\n{notes}")
            return
        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setText(f"发现新版本 {latest}，当前版本 {CURRENT_APP_VERSION}")
        box.setInformativeText(notes)
        update_button = box.addButton("立即更新", QMessageBox.AcceptRole)
        box.addButton("稍后提醒", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is update_button:
            self.download_update(download_url, str(data.get("sha256") or ""))

    def download_update(self, url: str, sha256: str) -> None:
        self.update_progress = QProgressDialog("正在下载新版本…", "取消", 0, 100, self)
        self.update_progress.setWindowTitle("软件更新")
        self.update_progress.setAutoClose(False)
        self.update_progress.setAutoReset(False)
        self.update_progress.show()
        task = UpdateDownloadTask(url, sha256)
        task.signals.progress.connect(self.update_progress.setValue)
        task.signals.finished.connect(self._on_update_downloaded)
        task.signals.failed.connect(self._on_update_download_failed)
        self.update_progress.canceled.connect(lambda: setattr(task, "url", ""))
        QThreadPool.globalInstance().start(task)

    def _on_update_download_failed(self, message: str) -> None:
        if self.update_progress:
            self.update_progress.close()
            self.update_progress = None
        QMessageBox.warning(self, "更新失败", message)

    def _on_update_downloaded(self, path: str) -> None:
        if self.update_progress:
            self.update_progress.close()
            self.update_progress = None
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            QApplication.quit()
        except OSError as exc:
            QMessageBox.warning(self, "更新失败", f"安装包已下载，但无法启动：{exc}\n{path}")


class Page(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 26, 28, 26)
        self.layout.setSpacing(14)


class PieChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.data: list[tuple[str, int, str]] = []
        self.setMinimumHeight(190)

    def set_data(self, data: list[tuple[str, int, str]]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        total = sum(max(0, value) for _, value, _ in self.data)
        if total <= 0:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无业务数据")
            painter.end()
            return
        colors = ["#4e75f6", "#16a085", "#f59e0b", "#ef6461"]
        chart_size = min(self.height() - 24, 150)
        chart_rect = QRectF(12, 12, chart_size, chart_size)
        start_angle = 0
        for index, (_, value, _) in enumerate(self.data):
            span_angle = round(max(0, value) / total * 360 * 16)
            painter.setBrush(QColor(colors[index % len(colors)]))
            painter.setPen(Qt.NoPen)
            painter.drawPie(chart_rect, start_angle, span_angle)
            start_angle += span_angle
        legend_x = int(chart_size + 30)
        for index, (label, value, color) in enumerate(self.data):
            y = 28 + index * 32
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(legend_x, y - 9, 10, 10, 3, 3)
            painter.setPen(QColor("#334155"))
            percent = value / total * 100 if total else 0
            painter.drawText(legend_x + 18, y, f"{label}  {value} ({percent:.0f}%)")
        painter.end()


class ProductRadarChart(QWidget):
    """八维商品雷达图，带旋转扫描线。"""

    def __init__(self) -> None:
        super().__init__()
        self.labels = [name for _, name in DIMENSION_LABELS]
        self.values = [7.0] * len(self.labels)
        self.scan_angle = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self.advance_scan)
        self.timer.start()
        self.setMinimumHeight(250)

    def set_values(self, values: list[float]) -> None:
        self.values = [max(0.0, min(10.0, float(value))) for value in values[:8]]
        self.values.extend([7.0] * (8 - len(self.values)))
        self.update()

    def advance_scan(self) -> None:
        self.scan_angle = (self.scan_angle + 2.5) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() * 0.47, self.height() * 0.52)
        radius = max(45.0, min(self.width() * 0.31, self.height() * 0.38))
        sides = len(self.labels)

        painter.setPen(QColor("#d8e2ec"))
        for ring in range(1, 6):
            points = []
            ring_radius = radius * ring / 5
            for index in range(sides):
                angle = -90 + index * 360 / sides
                points.append(QPointF(center.x() + ring_radius * math.cos(math.radians(angle)), center.y() + ring_radius * math.sin(math.radians(angle))))
            painter.drawPolygon(QPolygonF(points))
        for index in range(sides):
            angle = math.radians(-90 + index * 360 / sides)
            end = QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle))
            painter.drawLine(center, end)

        data_points = []
        for index, value in enumerate(self.values):
            angle = math.radians(-90 + index * 360 / sides)
            data_points.append(QPointF(center.x() + radius * value / 10 * math.cos(angle), center.y() + radius * value / 10 * math.sin(angle)))
        painter.setBrush(QColor(78, 117, 246, 60))
        painter.setPen(QColor("#4e75f6"))
        painter.drawPolygon(QPolygonF(data_points))

        scan_radians = math.radians(self.scan_angle - 90)
        scan_end = QPointF(center.x() + radius * math.cos(scan_radians), center.y() + radius * math.sin(scan_radians))
        painter.setPen(QColor(22, 160, 133, 180))
        painter.drawLine(center, scan_end)
        painter.setPen(QColor("#334155"))
        for index, label in enumerate(self.labels):
            angle = math.radians(-90 + index * 360 / sides)
            point = QPointF(center.x() + (radius + 16) * math.cos(angle), center.y() + (radius + 16) * math.sin(angle))
            painter.drawText(QRectF(point.x() - 35, point.y() - 9, 70, 18), Qt.AlignCenter, label)
        painter.end()


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




class DataDashboardPage(Page):
    """业务数据看板：核心指标、业务分布和商品雷达。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.layout.addWidget(make_title("数据看板", "查看选品、审核、衍生和货源匹配的业务数据。"))
        self.metrics = QGridLayout()
        self.metrics.setHorizontalSpacing(12)
        self.metrics.setVerticalSpacing(12)
        self.layout.addLayout(self.metrics)

        chart_row = QHBoxLayout()
        chart_row.setSpacing(14)
        pie_panel = QFrame()
        pie_panel.setObjectName("Panel")
        pie_layout = QVBoxLayout(pie_panel)
        pie_layout.setContentsMargins(16, 14, 16, 14)
        pie_layout.addWidget(QLabel("业务环节分布"))
        self.pie_chart = PieChart()
        pie_layout.addWidget(self.pie_chart, 1)
        chart_row.addWidget(pie_panel, 1)
        radar_panel = QFrame()
        radar_panel.setObjectName("Panel")
        radar_layout = QVBoxLayout(radar_panel)
        radar_layout.setContentsMargins(16, 14, 16, 14)
        radar_layout.addWidget(QLabel("商品雷达"))
        self.radar_chart = ProductRadarChart()
        radar_layout.addWidget(self.radar_chart, 1)
        chart_row.addWidget(radar_panel, 1)
        self.layout.addLayout(chart_row, 1)

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def refresh(self) -> None:
        try:
            status = self.gateway.pipeline_status() or {}
        except Exception:
            status = {}
        fastmoss = status.get("fastmoss") or {}
        derivation = status.get("derivation") or {}
        supplier = status.get("supplier") or {}
        review = status.get("review") or {}
        values = [
            ("新品商品", str(fastmoss.get("product_count") or 0), "FastMoss 入库"),
            ("衍生品", str(derivation.get("derived_count") or 0), "AI 生成"),
            ("1688 匹配", str(supplier.get("matched_count") or 0), "已补全货源"),
            ("审核记录", str(review.get("review_record_count") or 0), "教师批改"),
        ]
        while self.metrics.count():
            child = self.metrics.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, value in enumerate(values):
            self.metrics.addWidget(metric_card(*value), 0, index)
        for index in range(4):
            self.metrics.setColumnStretch(index, 1)
        self.pie_chart.set_data([
            ("新品商品", int(fastmoss.get("product_count") or 0), "#4e75f6"),
            ("衍生品", int(derivation.get("derived_count") or 0), "#16a085"),
            ("1688 匹配", int(supplier.get("matched_count") or 0), "#f59e0b"),
            ("审核记录", int(review.get("review_record_count") or 0), "#ef6461"),
        ])
        radar_values = [7.0] * 8
        try:
            derived_items = self.gateway.recommended_derived_products(1)
            if derived_items:
                level_map = {"极高": 9.5, "高": 8.0, "中": 6.0, "低": 4.0, "极低": 2.0}
                radar_values = []
                for _, level, _ in dimension_items_from_report(derived_items[0]):
                    stars = level.count("★") + level.count("⭐")
                    radar_values.append(float(stars * 2) if stars else next((value for key, value in level_map.items() if key in level), 6.0))
        except Exception:
            pass
        self.radar_chart.set_values(radar_values)



class PersonalCenterPage(Page):
    """账号资料、密码修改和积分充值入口。"""

    def __init__(self, gateway: DataGateway, on_theme_change=None, on_font_change=None) -> None:
        super().__init__()
        self.gateway = gateway
        self.layout.setSpacing(16)
        self.layout.addWidget(make_title("个人中心", "管理账号安全、积分余额和充值联系信息。"))

        profile = QFrame()
        profile.setObjectName("Panel")
        profile_layout = QGridLayout(profile)
        profile_layout.setContentsMargins(18, 16, 18, 16)
        profile_layout.setHorizontalSpacing(24)
        profile_layout.setVerticalSpacing(8)
        self.account_label = QLabel()
        self.role_label = QLabel()
        self.credit_label = QLabel()
        for label in (self.account_label, self.role_label, self.credit_label):
            label.setObjectName("PersonalValue")
        profile_layout.addWidget(QLabel("登录账号"), 0, 0)
        profile_layout.addWidget(self.account_label, 0, 1)
        profile_layout.addWidget(QLabel("账号角色"), 0, 2)
        profile_layout.addWidget(self.role_label, 0, 3)
        profile_layout.addWidget(QLabel("剩余积分"), 1, 0)
        profile_layout.addWidget(self.credit_label, 1, 1)
        profile_layout.setColumnStretch(1, 1)
        profile_layout.setColumnStretch(3, 1)
        self.layout.addWidget(profile)

        body = QHBoxLayout()
        body.setSpacing(16)
        password_panel = QFrame()
        password_panel.setObjectName("Panel")
        password_layout = QVBoxLayout(password_panel)
        password_layout.setContentsMargins(18, 16, 18, 18)
        password_layout.setSpacing(10)
        password_title = QLabel("修改密码")
        password_title.setObjectName("CardTitle")
        password_layout.addWidget(password_title)
        self.old_password = QLineEdit()
        self.old_password.setPlaceholderText("输入当前密码")
        self.old_password.setEchoMode(QLineEdit.Password)
        self.new_password = QLineEdit()
        self.new_password.setPlaceholderText("输入新密码（至少 6 位）")
        self.new_password.setEchoMode(QLineEdit.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setPlaceholderText("再次输入新密码")
        self.confirm_password.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(self.old_password)
        password_layout.addWidget(self.new_password)
        password_layout.addWidget(self.confirm_password)
        password_button = QPushButton("保存新密码")
        password_button.clicked.connect(self.save_password)
        password_layout.addWidget(password_button)
        password_layout.addStretch()
        body.addWidget(password_panel, 1)

        recharge_panel = QFrame()
        recharge_panel.setObjectName("Panel")
        recharge_layout = QVBoxLayout(recharge_panel)
        recharge_layout.setContentsMargins(18, 16, 18, 18)
        recharge_layout.setSpacing(10)
        recharge_title = QLabel("积分充值")
        recharge_title.setObjectName("CardTitle")
        recharge_layout.addWidget(recharge_title)
        recharge_hint = QLabel("扫码添加管理员好友，发送充值金额和账号。充值到账后积分会自动显示在这里。")
        recharge_hint.setObjectName("Muted")
        recharge_hint.setWordWrap(True)
        recharge_layout.addWidget(recharge_hint)
        recharge_button = QPushButton("扫码联系管理员")
        recharge_button.clicked.connect(self.show_recharge_qr)
        recharge_layout.addWidget(recharge_button)
        recharge_layout.addWidget(QLabel("充值记录"))
        record_hint = QLabel("充值记录功能已预留，后续接入微信支付或管理员审核后会显示明细。")
        record_hint.setObjectName("Muted")
        record_hint.setWordWrap(True)
        recharge_layout.addWidget(record_hint)
        recharge_layout.addStretch()
        body.addWidget(recharge_panel, 1)
        self.layout.addLayout(body)
        settings_panel = ThemeSettingsPanel(on_theme_change or (lambda _: None), on_font_change)
        self.layout.addWidget(settings_panel)
        self.layout.addStretch(1)
        self.refresh_profile()

    def activate(self) -> None:
        self.refresh_profile()

    def refresh_profile(self) -> None:
        user = self.gateway.user or {}
        self.account_label.setText(str(user.get("username") or "未登录"))
        role_map = {"admin": "系统管理员", "teacher": "选品老师", "student": "学生账号"}
        self.role_label.setText(role_map.get(str(user.get("role") or ""), str(user.get("role") or "未登录")))
        self.credit_label.setText(f"{int(user.get('credit_balance') or 0)} 积分")

    def save_password(self) -> None:
        old_password = self.old_password.text()
        new_password = self.new_password.text()
        if not old_password or not new_password:
            QMessageBox.information(self, "提示", "请完整填写密码。")
            return
        if new_password != self.confirm_password.text():
            QMessageBox.information(self, "提示", "两次输入的新密码不一致。")
            return
        try:
            result = self.gateway.change_password(old_password, new_password)
            QMessageBox.information(self, "修改成功", str(result.get("message") or "密码修改成功。"))
            self.old_password.clear()
            self.new_password.clear()
            self.confirm_password.clear()
        except Exception as exc:
            show_error_details(self, "修改密码失败", exc)

    def show_recharge_qr(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("积分充值")
        dialog.resize(360, 460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("扫码添加管理员好友")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        qr = QLabel()
        qr.setAlignment(Qt.AlignCenter)
        qr_path = Path(icon_path("recharge_qr.png"))
        if qr_path.exists():
            qr.setPixmap(QPixmap(str(qr_path)).scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            qr.setText("充值二维码待配置\n\n请将二维码图片放入：\nassets/icons/recharge_qr.png")
            qr.setObjectName("Muted")
        layout.addWidget(qr, 1)
        hint = QLabel("添加好友后发送：登录账号、充值金额和希望获得的积分。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()


class ThemeSettingsPanel(QFrame):
    def __init__(self, on_theme_change, on_font_change=None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("界面设置")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题皮肤"))
        self.theme_select = QComboBox()
        self.theme_select.addItem("深夜蓝", "midnight")
        self.theme_select.addItem("曜石黑", "obsidian")
        self.theme_select.addItem("浅色工作台", "light")
        self.theme_select.setCurrentIndex(2)
        self.theme_select.currentIndexChanged.connect(lambda: on_theme_change(str(self.theme_select.currentData())))
        theme_row.addWidget(self.theme_select, 1)
        layout.addLayout(theme_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("字体"))
        self.font_select = QComboBox()
        for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimSun"):
            self.font_select.addItem(family, family)
        self.font_select.setCurrentText("Microsoft YaHei UI")
        font_row.addWidget(self.font_select, 1)
        font_row.addWidget(QLabel("字号"))
        self.font_size = QComboBox()
        for size in ("12", "13", "14", "15", "16", "18"):
            self.font_size.addItem(f"{size}px", int(size))
        self.font_size.setCurrentText("14px")
        font_row.addWidget(self.font_size)
        layout.addLayout(font_row)

        def apply_font_setting() -> None:
            if on_font_change:
                on_font_change(str(self.font_select.currentData()), int(self.font_size.currentData()))

        self.font_select.currentIndexChanged.connect(apply_font_setting)
        self.font_size.currentIndexChanged.connect(apply_font_setting)
        hint = QLabel("主题和字体只影响当前软件界面，不影响账号、商品和后端数据。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)


class InfoPage(Page):
    def __init__(self, title: str, subtitle: str, content: str) -> None:
        super().__init__()
        self.layout.addWidget(make_title(title, subtitle))
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        text = QLabel(content)
        text.setObjectName("Muted")
        text.setWordWrap(True)
        panel_layout.addWidget(text)
        self.update_button = QPushButton("检查更新")
        self.update_button.setObjectName("StudioPrimary")
        self.update_button.setFixedWidth(140)
        panel_layout.addWidget(self.update_button, 0, Qt.AlignLeft)
        panel_layout.addStretch()
        self.layout.addWidget(panel, 1)


class VersionUpdatePage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.selected_file = ""
        self.layout.addWidget(make_title("版本更新", "上传安装包并发布桌面端版本"))

        form = QFrame()
        form.setObjectName("Panel")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(18, 18, 18, 18)
        form_layout.setSpacing(10)
        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("版本号"))
        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("例如：1.0.1")
        version_row.addWidget(self.version_input, 1)
        version_row.addWidget(QLabel("安装包"))
        self.file_label = QLabel("尚未选择")
        self.file_label.setObjectName("Muted")
        version_row.addWidget(self.file_label, 2)
        choose = QPushButton("选择安装包")
        choose.clicked.connect(self.choose_file)
        version_row.addWidget(choose)
        form_layout.addLayout(version_row)
        form_layout.addWidget(QLabel("更新说明"))
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("填写本次版本的更新内容")
        self.notes_input.setFixedHeight(100)
        form_layout.addWidget(self.notes_input)
        actions = QHBoxLayout()
        self.force_update = QCheckBox("强制更新")
        actions.addWidget(self.force_update)
        actions.addStretch()
        upload = QPushButton("上传并发布")
        upload.setObjectName("StudioPrimary")
        upload.clicked.connect(self.upload_release)
        actions.addWidget(upload)
        form_layout.addLayout(actions)
        self.status_label = QLabel("上传后将自动成为当前发布版本，旧版本会下架。")
        self.status_label.setObjectName("Muted")
        form_layout.addWidget(self.status_label)
        self.upload_button = upload
        self.layout.addWidget(form)

        self.release_table = QTableWidget(0, 6)
        self.release_table.setHorizontalHeaderLabels(["版本号", "安装包", "校验值", "状态", "发布时间", "操作"])
        self.release_table.verticalHeader().setVisible(False)
        self.release_table.verticalHeader().setDefaultSectionSize(58)
        self.release_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.release_table.setSelectionMode(QAbstractItemView.NoSelection)
        release_header = self.release_table.horizontalHeader()
        release_header.setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.release_table, 1)

    def activate(self) -> None:
        self.refresh()

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择版本安装包", "", "安装包 (*.exe *.zip)")
        if path:
            self.selected_file = path
            self.file_label.setText(Path(path).name)

    def upload_release(self) -> None:
        version = self.version_input.text().strip()
        if not version or not self.selected_file:
            QMessageBox.information(self, "资料不完整", "请填写版本号并选择安装包。")
            return
        self.upload_button.setEnabled(False)
        self.status_label.setText("正在上传安装包，请稍候…")
        QApplication.processEvents()
        try:
            self.gateway.upload_app_release(self.selected_file, version, self.notes_input.toPlainText(), self.force_update.isChecked())
            self.status_label.setText("发布成功，客户端下次启动时会检查到该版本。")
            QMessageBox.information(self, "发布成功", f"版本 {version} 已发布。")
            self.refresh()
        except Exception as exc:
            self.status_label.setText("发布失败")
            QMessageBox.warning(self, "发布失败", str(exc))
        finally:
            self.upload_button.setEnabled(True)

    def refresh(self) -> None:
        try:
            releases = self.gateway.app_releases()
        except Exception as exc:
            self.status_label.setText(f"读取版本列表失败：{exc}")
            return
        self.release_table.setRowCount(0)
        for row, item in enumerate(releases):
            self.release_table.insertRow(row)
            values = [
                item.get("version") or "",
                item.get("filename") or "",
                str(item.get("sha256") or "")[:16],
                "已发布" if item.get("status") else "已下架",
                item.get("published_at") or item.get("created_at") or "",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value))
                self.release_table.setItem(row, column, cell)
            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 2, 4, 2)
            publish = QPushButton("发布")
            publish.setMinimumHeight(38)
            publish.clicked.connect(lambda checked=False, release_id=int(item["id"]): self.publish_release(release_id))
            remove = QPushButton("删除")
            remove.setMinimumHeight(38)
            remove.clicked.connect(lambda checked=False, release_id=int(item["id"]): self.delete_release(release_id))
            action_layout.addWidget(publish)
            action_layout.addWidget(remove)
            self.release_table.setCellWidget(row, 5, actions)
            self.release_table.setRowHeight(row, 58)

    def publish_release(self, release_id: int) -> None:
        try:
            self.gateway.publish_app_release(release_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "发布失败", str(exc))

    def delete_release(self, release_id: int) -> None:
        if QMessageBox.question(self, "确认删除", "确定删除这个版本安装包吗？") != QMessageBox.Yes:
            return
        try:
            self.gateway.delete_app_release(release_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))


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
        result = self.gateway.queue_pending_derivations()
        if not result.get("ok"):
            QMessageBox.information(self, "提示", str(result.get("message") or result))
            return
        QMessageBox.information(self, "任务已提交", f"已加入后台衍生队列：{result.get('queued_count', 0)} 个原商品")
        self.refresh()

    def queue_supplier_matches(self) -> None:
        result = self.gateway.queue_supplier_matches()
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
            show_error_details(self, "加载失败", exc)
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
        self.full_update_task_id: int | None = None
        self.full_update_timer: QTimer | None = None
        self.layout.addWidget(make_title(title, "MVP 阶段先展示配置列表，后续补充新增、编辑、测试连接。"))
        action_bar = QFrame()
        action_bar.setObjectName("Toolbar")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(14, 12, 14, 12)
        add = QPushButton("新增配置")
        edit = QPushButton("编辑选中")
        toggle = QPushButton("启用/禁用")
        delete_button = QPushButton("删除选中")
        sync = QPushButton("同步 FastMoss")
        full_update = QPushButton("更新一批商品")
        add.clicked.connect(self.add_config)
        edit.clicked.connect(self.edit_config)
        toggle.clicked.connect(self.toggle_config)
        delete_button.clicked.connect(self.delete_config)
        sync.clicked.connect(self.sync_fastmoss)
        full_update.clicked.connect(self.update_batch)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addWidget(delete_button)
        if config_type == "third":
            actions.addWidget(sync)
            actions.addWidget(full_update)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.config_table = table(headers)
        self.layout.addWidget(self.config_table)
        if config_type == "third" and gateway:
            self.threshold_panel = BusinessThresholdPanel(gateway)
            self.layout.addWidget(self.threshold_panel)
        self.refresh()

    def activate(self) -> None:
        self.refresh()
        if hasattr(self, "threshold_panel"):
            self.threshold_panel.refresh()

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
            show_error_details(self, "加载失败", exc)
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
                    "使用中" if int(item.get("status") or 0) else "已停用",
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
            ("status", "是否使用中", "1=使用中，0=停用"),
            ("remark", "备注", ""),
        ]

    def third_fields(self) -> list[tuple[str, str, str]]:
        return [
            ("config_name", "配置名称", "阿里云短信"),
            ("service_type", "服务类型", "aliyun_sms/fastmoss/1688_api/custom_api/oxylabs/miaoshou/volcengine-mediakit"),
            ("api_base_url", "API 地址", "https://example.com"),
            ("access_key_encrypted", "Access Key", "API Key 或 Bearer Token"),
            ("secret_key_encrypted", "Secret Key", "可选"),
            ("sign_name", "短信签名", "阿里云控制台审核通过的签名名称"),
            ("template_code", "短信模板 Code", "例如 SMS_123456789"),
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
            main_window = self.window()
            if hasattr(main_window, "invalidate_product_pages"):
                main_window.invalidate_product_pages()
        except Exception as exc:
            QMessageBox.warning(self, "FastMoss 同步失败", str(exc))

    def update_batch(self) -> None:
        if not self.gateway or self.config_type != "third":
            return
        try:
            result = self.gateway.sync_fastmoss_products()
            derivation = result.get("derivation_result") or {}
            task_id = derivation.get("task_id")
            if not task_id:
                QMessageBox.information(self, "更新完成", "FastMoss 没有返回可执行的衍生任务。")
                return
            self.full_update_task_id = int(task_id)
            if self.full_update_timer:
                self.full_update_timer.stop()
            self.full_update_timer = QTimer(self)
            self.full_update_timer.setInterval(5000)
            self.full_update_timer.timeout.connect(self.poll_full_update)
            self.full_update_timer.start()
            QMessageBox.information(
                self,
                "完整流程已启动",
                f"FastMoss 已更新 {result.get('synced_count', 0)} 条商品，正在等待 AI 衍生完成，完成后会自动启动 1688 匹配。",
            )
            main_window = self.window()
            if hasattr(main_window, "invalidate_product_pages"):
                main_window.invalidate_product_pages()
        except Exception as exc:
            QMessageBox.warning(self, "更新失败", str(exc))

    def poll_full_update(self) -> None:
        if not self.gateway or not self.full_update_task_id:
            return
        try:
            status = self.gateway.pipeline_status()
            latest = (status.get("tasks") or {}).get("latest") or []
            task = next((item for item in latest if int(item.get("id") or 0) == self.full_update_task_id), None)
            if not task or task.get("status") not in {"success", "failed"}:
                return
            if self.full_update_timer:
                self.full_update_timer.stop()
            match_result = self.gateway.queue_supplier_matches()
            if not match_result.get("queued"):
                QMessageBox.warning(self, "1688 匹配未启动", str(match_result))
                return
            QMessageBox.information(
                self,
                "完整流程已进入 1688",
                f"AI 衍生任务已结束（成功 {task.get('success_count', 0)} 条），1688 匹配已自动加入后台队列。",
            )
        except Exception as exc:
            if self.full_update_timer:
                self.full_update_timer.stop()
            QMessageBox.warning(self, "流程状态查询失败", str(exc))


class ModelTestPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.items: list[dict[str, Any]] = []
        self.image_data_url = ""
        self.image_path = ""

        self.layout.addWidget(make_title("模型测试", "选择已配置模型，分别测试文本、图片和响应耗时。"))

        form = QFrame()
        form.setObjectName("Toolbar")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("测试模型"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(360)
        model_row.addWidget(self.model_combo)
        refresh_button = QPushButton("刷新模型")
        refresh_button.clicked.connect(self.refresh_models)
        model_row.addWidget(refresh_button)
        model_row.addStretch()
        form_layout.addLayout(model_row)

        text_label = QLabel("测试文本")
        text_label.setObjectName("FormLabel")
        form_layout.addWidget(text_label)
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("例如：请用中文简要说明这件商品适不适合日本 TikTok 销售。")
        self.text_edit.setMinimumHeight(120)
        form_layout.addWidget(self.text_edit)

        image_row = QHBoxLayout()
        image_row.addWidget(QLabel("图片"))
        self.image_url_edit = QLineEdit()
        self.image_url_edit.setPlaceholderText("可填写图片 URL，也可以选择本地图片")
        image_row.addWidget(self.image_url_edit, 1)
        choose_button = QPushButton("选择图片")
        choose_button.clicked.connect(self.choose_image)
        image_row.addWidget(choose_button)
        clear_button = QPushButton("清除图片")
        clear_button.clicked.connect(self.clear_image)
        image_row.addWidget(clear_button)
        form_layout.addLayout(image_row)

        action_row = QHBoxLayout()
        self.status_label = QLabel("准备测试")
        self.status_label.setObjectName("Muted")
        action_row.addWidget(self.status_label)
        action_row.addStretch()
        self.test_button = QPushButton("开始测试")
        self.test_button.setObjectName("PrimaryButton")
        self.test_button.clicked.connect(self.run_test)
        action_row.addWidget(self.test_button)
        form_layout.addLayout(action_row)
        self.layout.addWidget(form)

        result_header = QHBoxLayout()
        result_header.addWidget(QLabel("测试结果"))
        result_header.addStretch()
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("Muted")
        result_header.addWidget(self.meta_label)
        self.layout.addLayout(result_header)

        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("模型返回内容会显示在这里。")
        # QTextEdit 本身不设置字符上限，结果区域随窗口扩展，长结果通过内部滚动条完整保留。
        self.result_edit.setAcceptRichText(False)
        self.result_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self.result_edit.setMinimumHeight(420)
        self.layout.addWidget(self.result_edit, 1)
        self.refresh_models()

    def activate(self) -> None:
        self.refresh_models()

    def refresh_models(self) -> None:
        try:
            self.items = self.gateway.model_configs()
        except Exception as exc:
            self.items = []
            self.status_label.setText(f"模型读取失败：{exc}")
            return
        self.model_combo.clear()
        for item in self.items:
            label = f"{item.get('config_name') or item.get('model_name') or '未命名'} · {item.get('provider') or 'custom'} · {item.get('model_type') or 'general'}"
            self.model_combo.addItem(label, int(item.get("id") or 0))
        if self.items:
            self.status_label.setText(f"已加载 {len(self.items)} 个模型配置")
        else:
            self.status_label.setText("暂无模型配置，请先在模型配置中新增")

    def choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择测试图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.gif);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            if len(raw) > 8 * 1024 * 1024:
                QMessageBox.warning(self, "图片过大", "测试图片不能超过 8MB。")
                return
            mime = mimetypes.guess_type(path)[0] or "image/png"
            self.image_data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            self.image_path = path
            self.image_url_edit.setText(f"已选择：{Path(path).name}")
            self.image_url_edit.setToolTip(path)
        except OSError as exc:
            QMessageBox.warning(self, "读取图片失败", str(exc))

    def clear_image(self) -> None:
        self.image_data_url = ""
        self.image_path = ""
        self.image_url_edit.clear()
        self.image_url_edit.setToolTip("")

    def run_test(self) -> None:
        model_id = int(self.model_combo.currentData() or 0)
        if not model_id:
            QMessageBox.information(self, "提示", "请先选择一个模型配置。")
            return
        text = self.text_edit.toPlainText().strip()
        image_url = self.image_data_url or self.image_url_edit.text().strip()
        if not text and not image_url:
            QMessageBox.information(self, "提示", "请填写测试文本或提供一张图片。")
            return
        self.test_button.setEnabled(False)
        self.status_label.setText("正在调用模型，请稍候……")
        self.meta_label.setText("")
        self.result_edit.clear()
        QApplication.processEvents()
        try:
            result = self.gateway.test_model(model_id, text, image_url)
            elapsed = result.get("elapsed_ms", "-")
            config = next((item for item in self.items if int(item.get("id") or 0) == model_id), {})
            model_name = result.get("model_name") or config.get("model_name") or ""
            model_type = result.get("model_type") or config.get("model_type") or ""
            if result.get("ok"):
                self.status_label.setText("测试完成")
                self.meta_label.setText(f"{model_name} · {model_type} · {elapsed} ms")
                answer = str(result.get("answer") or "")
                output_path = self.save_test_result(answer, model_name, model_type, elapsed, True)
                self.result_edit.setPlainText(f"完整结果已写入文件：\n{output_path}\n\n{answer}")
            else:
                self.status_label.setText("模型调用失败")
                self.meta_label.setText(f"{model_name} · {model_type} · {elapsed} ms")
                error = str(result.get("error") or "未知错误")
                output_path = self.save_test_result(error, model_name, model_type, elapsed, False)
                self.result_edit.setPlainText(f"完整错误信息已写入文件：\n{output_path}\n\n{error}")
        except Exception as exc:
            self.status_label.setText("请求失败")
            self.result_edit.setPlainText(str(exc))
        finally:
            self.test_button.setEnabled(True)

    def save_test_result(self, content: str, model_name: str, model_type: str, elapsed: Any, success: bool) -> str:
        output_dir = APP_DIR / "data" / "model_test_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = output_dir / f"model_test_{timestamp}.txt"
        header = [
            "模型测试结果",
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"模型：{model_name}",
            f"类型：{model_type}",
            f"耗时：{elapsed} ms",
            f"状态：{'成功' if success else '失败'}",
            "=" * 60,
            "",
        ]
        output_path.write_text("\n".join(header) + content, encoding="utf-8")
        return str(output_path)


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
        delete_button = QPushButton("删除选中")
        add.clicked.connect(self.add_attribute)
        edit.clicked.connect(self.edit_attribute)
        toggle.clicked.connect(self.toggle_attribute)
        delete_button.clicked.connect(self.delete_attribute)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(toggle)
        actions.addWidget(delete_button)
        actions.addStretch()
        self.layout.addWidget(action_bar)
        self.attr_table = table(["ID", "属性", "类型", "当前权重", "状态"])
        self.layout.addWidget(self.attr_table)
        self.constant_panel = None
        if self.gateway.user and self.gateway.user.get("role") == "admin":
            self.constant_panel = PromptConstantPanel(self.gateway)
            self.layout.addWidget(self.constant_panel)
        self.refresh()

    def refresh(self) -> None:
        self.items = self.gateway.attributes()
        fill_table(self.attr_table, [[a.get("id"), a.get("attribute_name"), a.get("attribute_type"), a.get("current_weight"), "启用" if int(a.get("status", 1)) == 1 else "禁用"] for a in self.items])

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
        current = 1 if item.get("status") is None else int(item.get("status"))
        try:
            self.gateway.set_attribute_status(int(item["id"]), 0 if current else 1)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "状态更新失败", str(exc))

    def delete_attribute(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择属性。")
            return
        if QMessageBox.question(self, "确认删除", f"确定删除属性「{item.get('attribute_name', '')}」吗？") != QMessageBox.Yes:
            return
        try:
            self.gateway.delete_attribute(int(item["id"]))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))


class PromptConstantDialog(QDialog):
    def __init__(self, item: dict[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑大模型常量词表")
        self.resize(720, 520)
        item = item or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        title = QLabel("大模型常量词表")
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        self.key_edit = QLineEdit(str(item.get("constant_key") or ""))
        self.key_edit.setPlaceholderText("例如 jp_compliance_rules")
        self.name_edit = QLineEdit(str(item.get("constant_name") or ""))
        self.name_edit.setPlaceholderText("显示名称")
        for label, editor in (("常量编码", self.key_edit), ("常量名称", self.name_edit)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(editor, 1)
            layout.addLayout(row)
        layout.addWidget(QLabel("常量内容（每次调用相关大模型时会追加到提示词）"))
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(str(item.get("constant_content") or ""))
        self.content_edit.setMinimumHeight(260)
        layout.addWidget(self.content_edit, 1)
        self.remark_edit = QLineEdit(str(item.get("remark") or ""))
        self.remark_edit.setPlaceholderText("备注，可选")
        remark_row = QHBoxLayout()
        remark_row.addWidget(QLabel("备注"))
        remark_row.addWidget(self.remark_edit, 1)
        layout.addLayout(remark_row)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        save = QPushButton("保存")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def data(self) -> dict[str, Any]:
        return {
            "constant_key": self.key_edit.text().strip(),
            "constant_name": self.name_edit.text().strip(),
            "constant_content": self.content_edit.toPlainText().strip(),
            "status": 1,
            "remark": self.remark_edit.text().strip(),
        }


class PromptConstantPanel(QFrame):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.items: list[dict[str, Any]] = []
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        heading = QHBoxLayout()
        title = QLabel("大模型常量词表")
        title.setObjectName("CardTitle")
        hint = QLabel("编辑后会参与 AI 搜索和衍生品提示词组装")
        hint.setObjectName("Muted")
        heading.addWidget(title)
        heading.addWidget(hint)
        heading.addStretch()
        add = QPushButton("新增词表")
        edit = QPushButton("编辑选中")
        toggle = QPushButton("启用/禁用")
        delete_button = QPushButton("删除选中")
        add.clicked.connect(self.add_item)
        edit.clicked.connect(self.edit_item)
        toggle.clicked.connect(self.toggle_item)
        delete_button.clicked.connect(self.delete_item)
        for button in (add, edit, toggle, delete_button):
            heading.addWidget(button)
        layout.addLayout(heading)
        self.table = table(["ID", "名称", "编码", "内容摘要", "状态"])
        self.table.setMinimumHeight(150)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        try:
            self.items = self.gateway.prompt_constants()
        except Exception as exc:
            self.items = []
            if self.gateway.user and self.gateway.user.get("role") == "admin":
                QMessageBox.warning(self, "读取失败", str(exc))
        fill_table(
            self.table,
            [[item.get("id"), item.get("constant_name"), item.get("constant_key"), str(item.get("constant_content") or "")[:80], "启用" if int(item.get("status", 1)) else "禁用"] for item in self.items],
        )

    def selected_item(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def add_item(self) -> None:
        dialog = PromptConstantDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            try:
                self.gateway.save_prompt_constant(dialog.data())
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def edit_item(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择词表。")
            return
        dialog = PromptConstantDialog(item, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                self.gateway.save_prompt_constant(dialog.data(), int(item["id"]))
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def toggle_item(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择词表。")
            return
        try:
            self.gateway.set_prompt_constant_status(int(item["id"]), 0 if int(item.get("status", 1)) else 1)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "状态更新失败", str(exc))

    def delete_item(self) -> None:
        item = self.selected_item()
        if not item:
            QMessageBox.information(self, "提示", "请先选择词表。")
            return
        if QMessageBox.question(self, "确认删除", f"确定删除词表「{item.get('constant_name', '')}」吗？") != QMessageBox.Yes:
            return
        try:
            self.gateway.delete_prompt_constant(int(item["id"]))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))


class BusinessThresholdPanel(QFrame):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.setObjectName("Card")
        self.setting_inputs: dict[str, QSpinBox | QDoubleSpinBox] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        title = QLabel("业务阈值")
        title.setObjectName("CardTitle")
        hint = QLabel("修改后保存到服务器，FastMoss、衍生任务和 1688 匹配会使用最新值。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(title, 0, 0, 1, 2)
        layout.addWidget(hint, 1, 0, 1, 2)
        specs = [
            ("1688_match_threshold", "1688 图片匹配分数", "float"),
            ("1688_page_size", "1688 每页候选数", "int"),
            ("1688_max_candidates", "1688 最大候选数", "int"),
            ("1688_batch_limit", "1688 单次处理量", "int"),
            ("derivatives_per_product", "每个原商品衍生数量", "int"),
            ("fastmoss_page_size", "FastMoss 每次采集数", "int"),
        ]
        for row, (key, label_text, value_type) in enumerate(specs, start=2):
            layout.addWidget(QLabel(label_text), row, 0)
            if value_type == "float":
                field: QSpinBox | QDoubleSpinBox = QDoubleSpinBox()
                field.setRange(0, 100)
                field.setDecimals(1)
            else:
                field = QSpinBox()
                field.setRange(1, 500)
            field.setMinimumWidth(180)
            self.setting_inputs[key] = field
            layout.addWidget(field, row, 1)
        save = QPushButton("保存业务阈值")
        save.clicked.connect(self.save)
        layout.addWidget(save, len(specs) + 2, 0, 1, 2)

    def refresh(self) -> None:
        if not self.gateway.user:
            return
        try:
            items = self.gateway.system_settings()
        except Exception:
            return
        for item in items:
            field = self.setting_inputs.get(str(item.get("setting_key") or ""))
            if field:
                try:
                    field.setValue(float(item.get("setting_value") or 0))
                except (TypeError, ValueError):
                    pass

    def save(self) -> None:
        values = {key: str(field.value()) for key, field in self.setting_inputs.items()}
        try:
            self.gateway.update_system_settings(values)
            QMessageBox.information(self, "保存成功", "业务阈值已保存到服务器。")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))


class ThemePage(Page):
    def __init__(self, on_theme_change, on_font_change=None, gateway: DataGateway | None = None) -> None:
        super().__init__()
        self.on_theme_change = on_theme_change
        self.on_font_change = on_font_change
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

        font_panel = QFrame()
        font_panel.setObjectName("Card")
        font_layout = QGridLayout(font_panel)
        font_layout.setContentsMargins(18, 18, 18, 18)
        font_layout.setHorizontalSpacing(12)
        font_layout.setVerticalSpacing(10)
        font_title = QLabel("字体与字号")
        font_title.setObjectName("CardTitle")
        self.font_select = QComboBox()
        for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimSun"):
            self.font_select.addItem(family, family)
        self.font_select.setCurrentText("Microsoft YaHei UI")
        self.font_select.currentIndexChanged.connect(self.change_font)
        font_size_label = QLabel("字号")
        self.font_size = QComboBox()
        for size in ("12", "13", "14", "15", "16", "18"):
            self.font_size.addItem(f"{size}px", int(size))
        self.font_size.setCurrentText("14px")
        self.font_size.currentIndexChanged.connect(self.change_font)
        font_hint = QLabel("修改后立即应用到当前软件窗口，左侧菜单会同步更新。")
        font_hint.setObjectName("Muted")
        font_hint.setWordWrap(True)
        font_layout.addWidget(font_title, 0, 0, 1, 2)
        font_layout.addWidget(QLabel("字体"), 1, 0)
        font_layout.addWidget(self.font_select, 1, 1)
        font_layout.addWidget(font_size_label, 2, 0)
        font_layout.addWidget(self.font_size, 2, 1)
        font_layout.addWidget(font_hint, 3, 0, 1, 2)
        self.layout.addWidget(font_panel)

        self.layout.addStretch()

    def change_theme(self) -> None:
        self.on_theme_change(str(self.theme_select.currentData()))

    def change_font(self) -> None:
        if self.on_font_change:
            self.on_font_change(str(self.font_select.currentData()), int(self.font_size.currentData()))


def format_jpy_price(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,.0f}円"


def format_cny_price(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"¥{amount:,.2f}"


REGION_CURRENCY_SYMBOLS = {
    "JP": ("円", False),
    "KR": ("₩", False),
    "US": ("$", True),
    "ID": ("Rp", False),
    "GB": ("£", True),
    "VN": ("₫", False),
    "TH": ("฿", True),
    "MY": ("RM", True),
    "PH": ("₱", True),
    "ES": ("€", True),
    "MX": ("$", True),
    "DE": ("€", True),
    "FR": ("€", True),
    "IT": ("€", True),
    "BR": ("R$", True),
    "SG": ("S$", True),
}


def format_region_price(region: Any, value: Any, currency: Any = "") -> str:
    """Format prices using the product's market rather than a global JPY symbol."""
    region_code = str(region or "").strip().upper()
    currency_code = str(currency or "").strip().upper()
    if currency_code in {"CNY", "RMB"}:
        return format_cny_price(value)
    symbol, decimals = REGION_CURRENCY_SYMBOLS.get(region_code, ("円", False))
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{symbol}{amount:,.2f}" if decimals else f"{symbol}{amount:,.0f}"


def product_source_type(item: dict[str, Any]) -> str:
    snapshot = item.get("product_snapshot") if isinstance(item.get("product_snapshot"), dict) else {}
    if item.get("search_query") or snapshot.get("search_query"):
        return "ai_search"
    if item.get("list_type") or snapshot.get("list_type"):
        return "new_product"
    source = str(item.get("source_type") or "").lower()
    if source in {"derived", "new_product", "ai_search"}:
        return source
    return "derived"


def product_source_label(item: dict[str, Any]) -> str:
    return {
        "derived": "衍生品",
        "new_product": "新品榜",
        "ai_search": "AI搜索",
    }.get(product_source_type(item), "衍生品")


def format_sales_metric(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount >= 10000:
        return f"{amount / 10000:.1f}万"
    return f"{amount:,.0f}"


def report_summary_markup(sales: Any, score: Any) -> str:
    try:
        score_value = float(score or 0)
    except (TypeError, ValueError):
        score_value = 0
    return (
        '<table cellspacing="0" cellpadding="0" width="100%">'
        '<tr>'
        '<td width="52%" valign="top"><span style="color:#7b8798;font-size:12px;">销量</span><br/>'
        f'<span style="color:#24324a;font-size:21px;font-weight:800;">{format_sales_metric(sales)}</span></td>'
        '<td valign="top" align="right"><span style="color:#7b8798;font-size:12px;">AI参考分</span><br/>'
        f'<span style="color:#159878;font-size:21px;font-weight:800;">{score_value:.1f}</span></td>'
        '</tr></table>'
    )


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
        price_label = QLabel(format_region_price(item.get("region"), price, item.get("currency")))
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

        price_label = QLabel(format_region_price(item.get("region"), price, item.get("currency")))
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
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("推荐条数"))
        self.count_select = QComboBox()
        for label, value in (("10 条 · 10 积分", 10), ("15 条 · 15 积分", 15), ("20 条 · 20 积分", 20)):
            self.count_select.addItem(label, value)
        self.count_select.setCurrentIndex(0)
        self.count_select.setObjectName("StudioModeCombo")
        count_row.addWidget(self.count_select)
        count_row.addStretch()
        chat_layout.addLayout(count_row)
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
            result = self.gateway.start_ai_selection(text, int(self.count_select.currentData()))
        except Exception as exc:
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
                return
            if "积分不足" in str(exc):
                show_credit_recharge_prompt(self)
            else:
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
    def __init__(self, item: dict[str, Any], index: int, on_click=None, price_formatter=None) -> None:
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
        name_row = QHBoxLayout()
        name_row.setSpacing(5)
        name = QLabel(title[:14])
        name.setObjectName("StudioNewName")
        name.setWordWrap(True)
        name.setToolTip(title)
        name_row.addWidget(name, 1)
        if item.get("_is_latest_search"):
            new_tag = QLabel("NEW")
            new_tag.setObjectName("StudioNewTag")
            new_tag.setAlignment(Qt.AlignCenter)
            name_row.addWidget(new_tag, 0, Qt.AlignTop)
        layout.addLayout(name_row)
        metrics = QHBoxLayout()
        price_label = QLabel(price_formatter(price) if price_formatter else format_region_price(item.get("region"), price, item.get("currency")))
        price_label.setObjectName("StudioNewPrice")
        sales_label = QLabel(f"销量 {sales:,}")
        sales_label.setObjectName("StudioNewMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

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
        price_label = QLabel(format_region_price(item.get("region"), price, item.get("currency")))
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
        title_box = QHBoxLayout()
        title_box.setSpacing(8)
        title = QLabel("AI智能选品")
        title.setObjectName("StudioTitle")
        subtitle = QLabel("与AI对话，发现 TikTok Japan 热销商品")
        subtitle.setObjectName("Muted")
        title_box.addWidget(title)
        title_box.addWidget(QLabel("·"))
        title_box.addWidget(subtitle)
        title_box.addStretch()
        heading.addLayout(title_box)
        heading.addStretch()
        tutorial = QPushButton("◉  使用教程")
        tutorial.setObjectName("StudioTutorial")
        tutorial.clicked.connect(self.show_tutorial)
        heading.addWidget(tutorial)
        left_stack = QVBoxLayout()
        left_stack.setContentsMargins(0, 0, 0, 0)
        left_stack.setSpacing(14)
        left_stack.addLayout(heading)

        chat = QFrame()
        chat.setObjectName("StudioChat")
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(18, 15, 18, 15)
        chat_layout.setSpacing(9)
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        prompt_editor = PromptEditorFrame()
        prompt_editor.setMinimumHeight(116)
        self.chat_input = prompt_editor.editor
        self.chat_input.textChanged.connect(lambda: self._update_prompt_count(self.chat_input.toPlainText()))
        self.prompt_count = prompt_editor.count_label
        self.send_button = prompt_editor.analyze_button
        self._update_prompt_count(self.chat_input.toPlainText())
        self.send_button.clicked.connect(self.send_chat)
        prompt_row.addWidget(prompt_editor, 1)
        chat_layout.addLayout(prompt_row)
        count_row = QHBoxLayout()
        count_label = QLabel("推荐条数")
        count_label.setObjectName("StudioMarket")
        count_row.addWidget(count_label)
        self.count_select = QComboBox()
        for label, value in (("10 条 · 10 积分", 10), ("15 条 · 15 积分", 15), ("20 条 · 20 积分", 20)):
            self.count_select.addItem(label, value)
        self.count_select.setCurrentIndex(0)
        self.count_select.setObjectName("StudioModeCombo")
        self.count_select.currentIndexChanged.connect(
            lambda: prompt_editor.set_credit_cost(int(self.count_select.currentData() or 10))
        )
        self.count_select.currentIndexChanged.connect(self.refresh_credit_state)
        prompt_editor.set_credit_cost(int(self.count_select.currentData() or 10))
        count_row.addWidget(self.count_select)
        count_hint = QLabel("积分按推荐条数扣除")
        count_hint.setObjectName("StudioMarket")
        count_row.addWidget(count_hint)
        count_row.addStretch()
        chat_layout.addLayout(count_row)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        hot_label = QLabel("热门搜索：")
        hot_label.setObjectName("StudioMarket")
        chips.addWidget(hot_label)
        for text in ("厨房小工具", "收纳整理", "美姿个护", "宠物用品", "创意小物", "夏季用品"):
            chip = QPushButton(text)
            chip.setObjectName("StudioChip")
            chip.clicked.connect(lambda checked=False, value=text: self.chat_input.setPlainText(value))
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
        left_stack.addWidget(chat)

        workspace = QHBoxLayout()
        workspace.setSpacing(16)
        left_layout = left_stack

        new_header = QHBoxLayout()
        new_title = QLabel("今日选品推荐")
        new_title.setObjectName("StudioSectionTitle")
        new_meta = QLabel("AI 衍生品 · 日本站推荐")
        new_meta.setObjectName("StudioMarket")
        new_header.addWidget(new_title)
        new_header.addSpacing(8)
        new_header.addWidget(new_meta)
        new_header.addStretch()
        left_layout.addLayout(new_header)

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
        left_layout.addWidget(scroll, 1)
        workspace.addLayout(left_layout, 1)

        self.report_panel = QFrame()
        self.report_panel.setObjectName("StudioReport")
        self.report_panel.setFixedWidth(380)
        report_layout = QVBoxLayout(self.report_panel)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_layout.setSpacing(10)
        report_title = QLabel("选品分析报告")
        report_title.setObjectName("StudioPanelTitle")
        report_layout.addWidget(report_title)
        self.report_product = QLabel("选择商品查看分析")
        self.report_product.setObjectName("StudioReportTitle")
        self.report_product.setWordWrap(True)
        self.report_price = QLabel("")
        self.report_price.setObjectName("StudioReportPrice")
        self.report_image_box = QWidget()
        self.report_image_layout = QVBoxLayout(self.report_image_box)
        self.report_image_layout.setContentsMargins(0, 0, 0, 0)
        self.report_summary = QLabel("选择商品后显示销量和综合参考")
        self.report_summary.setObjectName("StudioSummaryText")
        self.report_summary.setWordWrap(True)
        report_product_info = QHBoxLayout()
        report_product_info.setSpacing(12)
        report_product_info.addWidget(self.report_image_box, 0)
        report_product_text = QVBoxLayout()
        report_product_text.setSpacing(6)
        report_product_text.addWidget(self.report_product)
        report_product_text.addWidget(self.report_price)
        report_product_text.addWidget(self.report_summary)
        report_product_text.addStretch()
        report_product_info.addLayout(report_product_text, 1)
        report_layout.addLayout(report_product_info)
        report_tabs = QHBoxLayout()
        report_tabs.setSpacing(4)
        self.report_tab_buttons: list[QPushButton] = []
        for tab_name in ("选品分析 1-6", "选品分析 7-8"):
            tab = QPushButton(tab_name)
            tab.setObjectName("StudioReportTab")
            tab.setCheckable(True)
            tab.setChecked(tab_name == "选品分析 1-6")
            tab.clicked.connect(lambda checked=False, name=tab_name, button=tab: self._select_report_tab(name, button))
            self.report_tab_buttons.append(tab)
            report_tabs.addWidget(tab)
        report_layout.addLayout(report_tabs)
        self.report_dimensions = QVBoxLayout()
        self.report_dimensions.setSpacing(6)
        report_layout.addLayout(self.report_dimensions)
        report_layout.addStretch(1)
        report_actions = QHBoxLayout()
        report_actions.setSpacing(8)
        self.favorite_button = QPushButton("☆  加入采集箱")
        self.favorite_button.setObjectName("StudioSecondaryAction")
        self.favorite_button.clicked.connect(self.toggle_favorite)
        self.start_button = QPushButton("⇩  导出报告")
        self.start_button.setObjectName("StudioPrimary")
        self.start_button.clicked.connect(self.export_report)
        report_actions.addWidget(self.favorite_button, 1)
        report_actions.addWidget(self.start_button, 1)
        report_layout.addLayout(report_actions)
        workspace.addWidget(self.report_panel)
        self.layout.addLayout(workspace, 1)
        self.report_item: dict[str, Any] | None = None
        self.report_tab = "选品分析 1-6"
        self.favorite_items: list[dict[str, Any]] = []
        self._show_report(None)

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
            "2. 点击“智能选品”，AI 会生成本次推荐结果。\n"
            "3. 下方今日选品推荐展示 AI 衍生品。\n"
            "4. 商品图片和销量以后台最新数据为准。",
        )

    def activate(self) -> None:
        if not self.loaded:
            self.refresh()
            self.loaded = True

    def refresh_credit_state(self) -> None:
        if hasattr(self, "send_button") and not self.selection_task_id:
            balance = int((self.gateway.user or {}).get("credit_balance") or 0)
            required = int(self.count_select.currentData() or 10)
            self.send_button.setEnabled(balance >= required)

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
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        try:
            result = self.gateway.start_ai_selection(text, int(self.count_select.currentData()))
        except Exception as exc:
            if "积分不足" in str(exc):
                show_credit_recharge_prompt(self)
            else:
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
            self.chat_input.setEnabled(True)
            self.send_button.setEnabled(True)
            QMessageBox.information(
                self,
                "选品完成",
                f"本次选品已完成，共生成 {status.get('success_count') or 0} 个商品。\n点击确定后进入选品库。",
            )
            parent = self.window()
            if hasattr(parent, "nav") and hasattr(parent, "pages"):
                for index, page in enumerate(parent.pages):
                    if isinstance(page, SelectionLibraryPage):
                        try:
                            page.refresh()
                            # Navigation rows also contain separators, so find
                            # the row by its stored page index instead of using
                            # the pages list index directly.
                            for row in range(parent.nav.count()):
                                nav_item = parent.nav.item(row)
                                if nav_item and nav_item.data(Qt.UserRole) == index:
                                    parent.nav.setCurrentRow(row)
                                    break
                        except Exception as exc:
                            show_error_details(self, "选品库加载失败", exc)
                        break
        elif status.get("status") == "failed":
            self.selection_timer.stop()
            self.chat_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.progress_label.setText("选品失败，积分已按后端结果处理")

    def _update_prompt_count(self, text: str) -> None:
        self.prompt_count.setText(f"{len(text)}/200")

    def load_favorites(self) -> None:
        try:
            self.favorite_items = self.gateway.favorites()
        except Exception as exc:
            self.favorite_items = []
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()

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
        self.favorite_button.setEnabled(bool(item))
        self.start_button.setEnabled(bool(item))
        if not item:
            self.report_product.setText("选择商品查看分析")
            self.report_price.clear()
            self.report_summary.setText("选择商品后显示销量和综合参考")
            self.favorite_button.setText("☆  加入采集箱")
            return
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        self.report_product.setText(title[:32])
        self.report_price.setText(format_region_price(item.get("region"), price, item.get("currency")))
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(report_summary_markup(sales, score))
        image = create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140)
        self.report_image_layout.addWidget(image)
        title_key = str(item.get("title") or item.get("derived_title") or "")
        image_key = str(item.get("image_url") or item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        self.favorite_button.setText("★  已在采集箱" if saved else "☆  加入采集箱")
        dimensions = dimension_items_from_report(item)
        dimensions = dimensions[:6] if self.report_tab == "选品分析 1-6" else dimensions[6:8]
        table = QFrame()
        table.setObjectName("StudioDimensionTable")
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        icons = ["◎", "≡", "↗", "◉", "◌", "▣", "♺", "△"]
        for index, (name, level, content) in enumerate(dimensions):
            row = QFrame()
            row.setObjectName("StudioDimensionRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setSpacing(8)
            icon = QLabel(icons[index % len(icons)])
            icon.setObjectName("StudioDimensionIcon")
            icon.setFixedSize(28, 28)
            icon.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(icon, 0, Qt.AlignTop)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            label = QLabel(name)
            label.setObjectName("StudioDimensionName")
            detail = QLabel(content or "暂无分析内容")
            detail.setObjectName("StudioDimensionText")
            detail.setWordWrap(True)
            copy.addWidget(label)
            copy.addWidget(detail)
            row_layout.addLayout(copy, 1)
            grade = QLabel(level or "参考")
            grade.setObjectName("StudioDimensionGrade")
            row_layout.addWidget(grade, 0, Qt.AlignTop)
            table_layout.addWidget(row)
        self.report_dimensions.addWidget(table)

    def toggle_favorite(self) -> None:
        if not self.report_item:
            return
        title_key = str(self.report_item.get("title") or self.report_item.get("derived_title") or "")
        image_key = str(self.report_item.get("image_url") or self.report_item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        try:
            if saved:
                self.gateway.delete_favorite(int(saved["id"]))
                self.favorite_items = [favorite for favorite in self.favorite_items if int(favorite.get("id") or 0) != int(saved["id"])]
            else:
                saved = self.gateway.create_favorite(self.report_item)
                self.favorite_items.insert(0, saved)
            self._show_report(self.report_item)
        except Exception as exc:
            QMessageBox.warning(self, "采集失败", str(exc))

    def export_report(self) -> None:
        if not self.report_item:
            return
        title = str(self.report_item.get("title") or self.report_item.get("derived_title") or "")
        try:
            output_dir = APP_DIR / "data" / "selection_reports"
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_title = "".join(char for char in title[:24] if char not in '\\/:*?"<>|') or "商品"
            output_path = output_dir / f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            output_path.write_text(json.dumps(self.report_item, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "报告已导出", f"完整报告已保存：\n{output_path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _select_report_tab(self, name: str, button: QPushButton) -> None:
        self.report_tab = name
        for tab in self.report_tab_buttons:
            tab.setChecked(tab is button)
        self._show_report(self.report_item)

    def refresh(self) -> None:
        self.load_favorites()
        items = self.gateway.recommended_derived_products()
        while self.new_product_grid.count():
            child = self.new_product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for index, item in enumerate(items):
            self.new_product_grid.addWidget(StudioNewProductCard(item, index, self._show_report), index // 6, index % 6)
        self.new_product_grid.setColumnStretch(6, 1)
        if items and not self.report_item:
            self._show_report(items[0])


class SelectionLibraryPage(Page):
    """当前用户 AI 搜索结果选品库。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.report_item: dict[str, Any] | None = None
        self.report_tab = "选品分析 1-6"
        self.favorite_items: list[dict[str, Any]] = []
        self.layout.setContentsMargins(28, 22, 28, 22)
        self.layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("选品库")
        title.setObjectName("StudioTitle")
        subtitle = QLabel("查看当前账号最近 7 天的 AI 搜索选品结果")
        subtitle.setObjectName("Muted")
        header.addWidget(title)
        header.addWidget(QLabel("·"))
        header.addWidget(subtitle)
        header.addStretch()

        attribute_box = QFrame()
        attribute_box.setObjectName("LibraryAttributes")
        attribute_layout = QVBoxLayout(attribute_box)
        attribute_layout.setContentsMargins(14, 12, 14, 12)
        attribute_layout.setSpacing(8)
        attribute_heading = QHBoxLayout()
        attribute_icon = QLabel("✦")
        attribute_icon.setObjectName("StudioReportIcon")
        attribute_heading.addWidget(attribute_icon)
        attribute_title = QLabel("选品属性维度")
        attribute_title.setObjectName("StudioPanelTitle")
        attribute_heading.addWidget(attribute_title)
        attribute_heading.addStretch()
        attribute_layout.addLayout(attribute_heading)
        self.attribute_grid = QGridLayout()
        self.attribute_grid.setHorizontalSpacing(10)
        self.attribute_grid.setVerticalSpacing(8)
        self.attribute_grid.setContentsMargins(0, 0, 0, 0)
        attribute_layout.addLayout(self.attribute_grid)
        self.attribute_box = attribute_box
        self.attribute_box.hide()

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addLayout(header)
        left_layout.addWidget(self.attribute_box)
        library_filter_panel = QFrame()
        library_filter_panel.setObjectName("RankFilterPanel")
        library_filter_layout = QVBoxLayout(library_filter_panel)
        library_filter_layout.setContentsMargins(0, 0, 0, 8)
        library_filter_layout.setSpacing(6)

        def add_library_option(row: QHBoxLayout, text: str, value: str, group: list[QPushButton]) -> None:
            button = QPushButton(text)
            button.setObjectName("RankFilterOption")
            button.setCheckable(True)
            button.setAutoExclusive(False)
            button.setFocusPolicy(Qt.NoFocus)
            button.setProperty("filter_value", value)
            button.clicked.connect(lambda checked=False, current=button: self._select_library_filter(current, group))
            group.append(button)
            row.addWidget(button)

        region_row = QHBoxLayout()
        region_row.setSpacing(4)
        region_label = QLabel("国家/地区：")
        region_label.setObjectName("RankFilterLabel")
        region_row.addWidget(region_label)
        self.library_region_buttons: list[QPushButton] = []
        library_regions = (("全部", "ALL"), ("美国", "US"), ("英国", "GB"), ("东南亚", "SEA"), ("日本", "JP"))
        for label, code in library_regions:
            add_library_option(region_row, label, code, self.library_region_buttons)
        self.library_region_buttons[0].setChecked(True)
        region_row.addStretch()
        library_filter_layout.addLayout(region_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(4)
        category_label = QLabel("商品分类：")
        category_label.setObjectName("RankFilterLabel")
        category_row.addWidget(category_label)
        self.library_category_buttons: list[QPushButton] = []
        library_categories = ("全部", "美妆个护", "女装与女士内衣", "保健", "时尚配件", "运动与户外", "手机与数码", "居家日用", "食品饮料", "玩具和爱好")
        for label in library_categories:
            add_library_option(category_row, label, label, self.library_category_buttons)
        self.library_category_buttons[0].setChecked(True)
        category_row.addStretch()
        library_filter_layout.addLayout(category_row)
        self.library_filter_panel = library_filter_panel
        left_layout.addWidget(self.library_filter_panel)
        list_header = QHBoxLayout()
        list_title = QLabel("我的搜索选品")
        list_title.setObjectName("StudioSectionTitle")
        self.list_title = list_title
        list_header.addWidget(list_title)
        list_header.addStretch()
        left_layout.addLayout(list_header)
        scroll = QScrollArea()
        scroll.setObjectName("StudioScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("StudioGrid")
        self.product_grid = QGridLayout(content)
        self.product_grid.setContentsMargins(4, 4, 4, 18)
        self.product_grid.setHorizontalSpacing(12)
        self.product_grid.setVerticalSpacing(12)
        self.product_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content)
        left_layout.addWidget(scroll, 1)
        body.addWidget(left, 1)

        self.report_panel = QFrame()
        self.report_panel.setObjectName("StudioReport")
        self.report_panel.setFixedWidth(380)
        report_layout = QVBoxLayout(self.report_panel)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_layout.setSpacing(10)
        report_title = QLabel("选品分析报告")
        report_title.setObjectName("StudioPanelTitle")
        report_layout.addWidget(report_title)
        self.report_product = QLabel("选择商品查看分析")
        self.report_product.setObjectName("StudioReportTitle")
        self.report_product.setWordWrap(True)
        self.report_price = QLabel("")
        self.report_price.setObjectName("StudioReportPrice")
        self.report_image_box = QWidget()
        self.report_image_layout = QVBoxLayout(self.report_image_box)
        self.report_image_layout.setContentsMargins(0, 0, 0, 0)
        self.report_summary = QLabel("选择商品后显示销量和综合参考")
        self.report_summary.setObjectName("StudioSummaryText")
        self.report_summary.setWordWrap(True)
        report_product_info = QHBoxLayout()
        report_product_info.setSpacing(12)
        report_product_info.addWidget(self.report_image_box, 0)
        report_product_text = QVBoxLayout()
        report_product_text.setSpacing(6)
        report_product_text.addWidget(self.report_product)
        report_product_text.addWidget(self.report_price)
        report_product_text.addWidget(self.report_summary)
        report_product_text.addStretch()
        report_product_info.addLayout(report_product_text, 1)
        report_layout.addLayout(report_product_info)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.report_tab_buttons: list[QPushButton] = []
        for tab_name in ("选品分析 1-6", "选品分析 7-8"):
            tab = QPushButton(tab_name)
            tab.setObjectName("StudioReportTab")
            tab.setCheckable(True)
            tab.setChecked(tab_name == self.report_tab)
            tab.clicked.connect(lambda checked=False, name=tab_name, button=tab: self._select_report_tab(name, button))
            self.report_tab_buttons.append(tab)
            tabs.addWidget(tab)
        report_layout.addLayout(tabs)
        dimensions_scroll = QScrollArea()
        dimensions_scroll.setObjectName("StudioScroll")
        dimensions_scroll.setWidgetResizable(True)
        dimensions_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dimensions_content = QWidget()
        self.report_dimensions = QVBoxLayout(dimensions_content)
        self.report_dimensions.setContentsMargins(0, 0, 2, 0)
        self.report_dimensions.setSpacing(6)
        self.report_dimensions.setAlignment(Qt.AlignTop)
        dimensions_scroll.setWidget(dimensions_content)
        report_layout.addWidget(dimensions_scroll, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.favorite_button = QPushButton("☆  加入采集箱")
        self.favorite_button.setObjectName("StudioSecondaryAction")
        self.favorite_button.clicked.connect(self.toggle_favorite)
        self.start_button = QPushButton("⇩  导出报告")
        self.start_button.setObjectName("StudioPrimary")
        self.start_button.clicked.connect(self.export_report)
        actions.addWidget(self.favorite_button, 1)
        actions.addWidget(self.start_button, 1)
        report_layout.addLayout(actions)
        body.addWidget(self.report_panel)
        self.layout.addLayout(body, 1)
        self._show_report(None)

    def activate(self) -> None:
        # 每次进入选品库都重新读取，确保刚加入的商品立即可见。
        self.load_favorites()
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

    def load_favorites(self) -> None:
        try:
            self.favorite_items = self.gateway.favorites()
        except Exception as exc:
            self.favorite_items = []
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()

    def refresh(self) -> None:
        while self.product_grid.count():
            child = self.product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        items = self.gateway.user_search_results()
        task_ids = [int(item.get("task_id") or 0) for item in items if item.get("task_id")]
        latest_task_id = max(task_ids, default=0)
        for item in items:
            item["_is_latest_search"] = bool(
                latest_task_id and int(item.get("task_id") or 0) == latest_task_id
            )
        self._update_library_category_state(items)
        items = [item for item in items if self._matches_library_filter(item)]
        if not items:
            empty = QLabel("暂无搜索选品，请先在智能选品对话框提交需求。")
            empty.setObjectName("Muted")
            self.product_grid.addWidget(empty, 0, 0)
            return
        for index, item in enumerate(items):
            self.product_grid.addWidget(StudioNewProductCard(item, index, self._show_report), index // 6, index % 6)
        self.product_grid.setColumnStretch(6, 1)
        self.report_item = None

    def refresh_attributes(self) -> None:
        while self.attribute_grid.count():
            child = self.attribute_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        try:
            attributes = self.gateway.attributes()
        except Exception:
            attributes = []
        by_code = {str(item.get("attribute_code") or ""): item for item in attributes}
        for index, (code, default_name) in enumerate(DIMENSION_LABELS):
            item = by_code.get(code, {})
            name = str(item.get("attribute_name") or default_name)
            weight = item.get("current_weight") or item.get("default_weight")
            description = str(item.get("description") or "用于衍生品分析和审核反馈")
            card = QFrame()
            card.setObjectName("LibraryAttributeCard")
            card.setToolTip(description)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(9, 6, 9, 6)
            card_layout.setSpacing(5)
            icon_label = QLabel("✦")
            icon_label.setObjectName("StudioReportIcon")
            icon_label.setFixedWidth(18)
            icon_label.setAlignment(Qt.AlignCenter)
            name_label = QLabel(name)
            name_label.setObjectName("LibraryAttributeName")
            value_label = QLabel(f"{float(weight) * 100:.0f}%" if weight is not None else "默认")
            value_label.setObjectName("LibraryAttributeValue")
            card_layout.addWidget(icon_label)
            card_layout.addWidget(name_label)
            card_layout.addStretch()
            card_layout.addWidget(value_label)
            self.attribute_grid.addWidget(card, index // 4, index % 4)
        for column in range(4):
            self.attribute_grid.setColumnStretch(column, 1)

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
        self.favorite_button.setEnabled(bool(item))
        self.start_button.setEnabled(bool(item))
        if not item:
            self.report_product.setText("选择商品查看分析")
            self.report_price.clear()
            self.report_summary.setText("选择商品后显示销量和综合参考")
            self.favorite_button.setText("☆  加入采集箱")
            return
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        price = item.get("supplier_price") or item.get("price") or item.get("suggested_price_min") or 0
        self.report_product.setText(title[:32])
        self.report_price.setText(format_region_price(item.get("region"), price, item.get("currency")))
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(report_summary_markup(sales, score))
        self.report_image_layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140))
        title_key = str(item.get("title") or item.get("derived_title") or "")
        image_key = str(item.get("image_url") or item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        self.favorite_button.setText("★  已在采集箱" if saved else "☆  加入采集箱")
        dimensions = dimension_items_from_report(item)
        dimensions = dimensions[:6] if self.report_tab == "选品分析 1-6" else dimensions[6:8]
        table = QFrame()
        table.setObjectName("StudioDimensionTable")
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        icons = ["◎", "≡", "↗", "◉", "◌", "▣", "♺", "△"]
        for index, (name, level, detail_text) in enumerate(dimensions):
            row = QFrame()
            row.setObjectName("StudioDimensionRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setSpacing(8)
            icon = QLabel(icons[index % len(icons)])
            icon.setObjectName("StudioDimensionIcon")
            icon.setFixedSize(28, 28)
            icon.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(icon, 0, Qt.AlignTop)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            label = QLabel(name)
            label.setObjectName("StudioDimensionName")
            detail = QLabel(detail_text or "暂无分析内容")
            detail.setObjectName("StudioDimensionText")
            detail.setWordWrap(True)
            copy.addWidget(label)
            copy.addWidget(detail)
            row_layout.addLayout(copy, 1)
            grade = QLabel(level or "参考")
            grade.setObjectName("StudioDimensionGrade")
            row_layout.addWidget(grade, 0, Qt.AlignTop)
            table_layout.addWidget(row)
        self.report_dimensions.addWidget(table)

    def _select_report_tab(self, name: str, button: QPushButton) -> None:
        self.report_tab = name
        for tab in self.report_tab_buttons:
            tab.setChecked(tab is button)
        self._show_report(self.report_item)

    def toggle_favorite(self) -> None:
        if not self.report_item:
            return
        title_key = str(self.report_item.get("title") or self.report_item.get("derived_title") or "")
        image_key = str(self.report_item.get("image_url") or self.report_item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        try:
            if saved:
                self.gateway.delete_favorite(int(saved["id"]))
                self.favorite_items = [favorite for favorite in self.favorite_items if int(favorite.get("id") or 0) != int(saved["id"])]
            else:
                saved = self.gateway.create_favorite(self.report_item)
                self.favorite_items.insert(0, saved)
            self._show_report(self.report_item)
        except Exception as exc:
            QMessageBox.warning(self, "采集失败", str(exc))

    def _select_library_filter(self, button: QPushButton, group: list[QPushButton]) -> None:
        for item in group:
            item.setChecked(item is button)
        self.refresh()

    @staticmethod
    def _collection_field(item: dict[str, Any], field: str) -> str:
        snapshot = item.get("product_snapshot") if isinstance(item.get("product_snapshot"), dict) else {}
        raw = snapshot.get("supplier_raw_data") or snapshot.get("raw_data") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        if field == "region":
            return str(item.get("region") or snapshot.get("region") or snapshot.get("country") or "日本")
        if field == "category":
            return str(
                item.get("supplier_category")
                or snapshot.get("supplier_category")
                or raw.get("category")
                or raw.get("category_name")
                or item.get("category")
                or snapshot.get("category")
                or "未分类"
            )
        return ""

    def _matches_library_filter(self, item: dict[str, Any]) -> bool:
        region = self._selected_library_value(self.library_region_buttons, "ALL")
        category = self._selected_library_value(self.library_category_buttons, "全部")
        item_region = self._collection_field(item, "region").upper()
        item_category = self._collection_field(item, "category")
        region_match = region == "ALL" or item_region == region or (
            region == "SEA" and item_region in {"ID", "VN", "TH", "MY", "PH", "SG"}
        )
        return region_match and (category == "全部" or category in item_category)

    def _update_library_category_state(self, items: list[dict[str, Any]]) -> None:
        """地区变化后同步分类选项，地区与分类始终共同过滤。"""
        region = self._selected_library_value(self.library_region_buttons, "ALL")
        available: set[str] = set()
        for item in items:
            item_region = self._collection_field(item, "region").upper()
            if region == "ALL" or item_region == region or (
                region == "SEA" and item_region in {"ID", "VN", "TH", "MY", "PH", "SG"}
            ):
                available.add(self._collection_field(item, "category"))
        for button in self.library_category_buttons:
            value = str(button.property("filter_value") or "")
            button.setEnabled(value == "全部" or not available or any(value in category for category in available))
        selected = next((button for button in self.library_category_buttons if button.isChecked()), None)
        if selected and not selected.isEnabled():
            self.library_category_buttons[0].setChecked(True)

    @staticmethod
    def _selected_library_value(buttons: list[QPushButton], default: str) -> str:
        for button in buttons:
            if button.isChecked():
                return str(button.property("filter_value") or default)
        return default

    def export_report(self) -> None:
        if not self.report_item:
            return
        title = str(self.report_item.get("title") or self.report_item.get("derived_title") or "")
        try:
            output_dir = APP_DIR / "data" / "selection_reports"
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_title = "".join(char for char in title[:24] if char not in '\\/:*?"<>|') or "商品"
            output_path = output_dir / f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            output_path.write_text(json.dumps(self.report_item, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "报告已导出", f"完整报告已保存：\n{output_path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))


class NewProductsPage(SelectionLibraryPage):
    """新品榜单页面，使用 FastMoss 最新入库商品。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__(gateway)
        filter_panel = QFrame()
        filter_panel.setObjectName("RankFilterPanel")
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.setContentsMargins(0, 0, 0, 8)
        filter_layout.setSpacing(8)

        def add_filter_option(row: QHBoxLayout, text: str, value: str, group: list[QPushButton], callback=None) -> QPushButton:
            button = QPushButton(text)
            button.setObjectName("RankFilterOption")
            button.setCheckable(True)
            button.setAutoExclusive(False)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda checked=False, current=button: self._select_filter_option(current, group, callback))
            group.append(button)
            row.addWidget(button)
            return button

        first_row = QHBoxLayout()
        first_row.setSpacing(4)
        time_label = QLabel("上架时间：")
        time_label.setObjectName("RankFilterLabel")
        first_row.addWidget(time_label)
        today = QDate.currentDate()
        self.start_date_edit = QDateEdit(today.addDays(-30))
        self.start_date_edit.setObjectName("RankFilterDate")
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        first_row.addWidget(self.start_date_edit)
        arrow = QLabel("→")
        arrow.setObjectName("RankFilterLabel")
        first_row.addWidget(arrow)
        self.end_date_edit = QDateEdit(today)
        self.end_date_edit.setObjectName("RankFilterDate")
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        first_row.addWidget(self.end_date_edit)
        self.start_date_edit.dateChanged.connect(lambda _: self.force_refresh())
        self.end_date_edit.dateChanged.connect(lambda _: self.force_refresh())
        first_row.addStretch()
        self.sync_rank_button = QPushButton("同步当前榜单")
        self.sync_rank_button.setObjectName("StudioSecondaryAction")
        self.sync_rank_button.clicked.connect(self.sync_current_rank)
        self.view_derivable_button = QPushButton("查看可衍生品")
        self.view_derivable_button.setObjectName("RankFilterViewButton")
        self.view_derivable_button.clicked.connect(self.show_japan_new_products)
        first_row.addWidget(self.sync_rank_button)
        first_row.addWidget(self.view_derivable_button)
        filter_layout.addLayout(first_row)

        region_row = QHBoxLayout()
        region_row.setSpacing(4)
        region_label = QLabel("国家/地区：")
        region_label.setObjectName("RankFilterLabel")
        region_row.addWidget(region_label)
        self.region_options: list[QPushButton] = []
        region_values = (
            ("全部", "ALL"), ("美国", "US"), ("印度尼西亚", "ID"), ("英国", "GB"),
            ("越南", "VN"), ("泰国", "TH"), ("马来西亚", "MY"), ("菲律宾", "PH"),
            ("西班牙", "ES"), ("墨西哥", "MX"), ("德国", "DE"), ("法国", "FR"),
            ("意大利", "IT"), ("巴西", "BR"), ("日本", "JP"), ("新加坡", "SG"),
        )
        self.region_buttons: list[QPushButton] = []
        for label, code in region_values:
            button = add_filter_option(region_row, label, code, self.region_buttons, self._region_changed)
            button.setProperty("filter_value", code)
        self.region_buttons[0].setChecked(False)
        self.region_buttons[1].setChecked(False)
        self.region_buttons[14].setChecked(True)
        region_row.addStretch()
        filter_layout.addLayout(region_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(4)
        category_label = QLabel("商品分类：")
        category_label.setObjectName("RankFilterLabel")
        category_row.addWidget(category_label)
        self.category_buttons: list[QPushButton] = []
        for label in ("全部", "美妆个护", "女装与女士内衣", "保健", "时尚配件", "运动与户外", "手机与数码", "居家日用", "食品饮料", "汽车与摩托车", "男装与男士内衣", "收藏品", "玩具和爱好"):
            button = add_filter_option(category_row, label, label, self.category_buttons, self._category_changed)
            button.setProperty("filter_value", label)
        self.category_buttons[0].setChecked(True)
        category_row.addStretch()
        filter_layout.addLayout(category_row)

        rank_row = QHBoxLayout()
        rank_row.setSpacing(4)
        rank_label = QLabel("商品榜单：")
        rank_label.setObjectName("RankFilterLabel")
        rank_row.addWidget(rank_label)
        self.rank_buttons: list[QPushButton] = []
        for label, code in (("销量榜", "sales"), ("新品榜", "new"), ("热销榜", "hot")):
            button = add_filter_option(rank_row, label, code, self.rank_buttons, self._rank_changed)
            button.setProperty("filter_value", code)
        self.rank_buttons[1].setChecked(True)
        rank_row.addStretch()
        filter_layout.addLayout(rank_row)
        self.layout.insertWidget(0, filter_panel)
        self.attribute_box.hide()
        self.library_filter_panel.hide()
        self.report_panel.hide()
        self.list_title.hide()
        for label in self.findChildren(QLabel):
            if label.text() == "选品库":
                self.page_title = label
                label.hide()
            elif label.text() == "查看当前账号最近 7 天的 AI 搜索选品结果":
                self.page_subtitle = label
                label.hide()
            elif label.text() == "我的搜索选品":
                self.page_title = label
                label.setText("新品榜单")

    def refresh(self) -> None:
        rank_names = {"new": "新品榜单", "hot": "热销榜", "sales": "销量榜"}
        current_rank = str(self._selected_value(self.rank_buttons, "new"))
        current_region = str(self._selected_value(self.region_buttons, "JP"))
        current_category = str(self._selected_value(self.category_buttons, "全部"))
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        self.rank_code = current_rank
        self.region_code = current_region
        self.category_code = current_category
        self.page_title.setText(rank_names.get(current_rank, "榜单商品"))
        while self.product_grid.count():
            child = self.product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.load_favorites()
        items = self.gateway.daily_recommendations(current_region, current_rank, current_category, start_date, end_date)
        if not items:
            empty = QLabel("暂无新品榜单数据，请先同步 FastMoss。")
            empty.setObjectName("Muted")
            self.product_grid.addWidget(empty, 0, 0)
            return
        for index, item in enumerate(items):
            can_derive = str(item.get("region") or "").upper() == "JP" and str(item.get("list_type") or "").lower() == "new"
            self.product_grid.addWidget(
                TeacherProductCard(item, self.open_derivable_product, can_derive=can_derive, on_collect=self.add_to_library),
                index // 6,
                index % 6,
            )
        self.product_grid.setColumnStretch(8, 1)

    def open_derivable_product(self, product: dict[str, Any]) -> None:
        dialog = DerivedDialog(self.gateway, product, [product], 0, self, review_mode=False)
        dialog.exec()
        self.refresh()

    def add_to_library(self, product: dict[str, Any], button: QPushButton | None = None) -> None:
        try:
            self.gateway.add_to_selection_library(product)
            if button is not None:
                button.setText("已加入选品库")
                button.setEnabled(False)
            QMessageBox.information(self, "加入成功", "商品已加入当前账号的选品库。")
        except Exception as exc:
            QMessageBox.warning(self, "加入失败", str(exc))

    def sync_current_rank(self) -> None:
        try:
            self.sync_rank_button.setEnabled(False)
            self.gateway.sync_fastmoss_products(getattr(self, "region_code", "JP"), getattr(self, "rank_code", "new"))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "同步失败", str(exc))
        finally:
            self.sync_rank_button.setEnabled(True)

    def show_japan_new_products(self) -> None:
        for button in self.region_buttons:
            button.setChecked(button.property("filter_value") == "JP")
        for button in self.rank_buttons:
            button.setChecked(button.property("filter_value") == "new")
        for button in self.category_buttons:
            button.setChecked(button.property("filter_value") == "全部")
        self.force_refresh()

    @staticmethod
    def _selected_value(buttons: list[QPushButton], default: str) -> str:
        for button in buttons:
            if button.isChecked():
                return str(button.property("filter_value") or default)
        return default

    @staticmethod
    def _select_filter_option(button: QPushButton, group: list[QPushButton], callback=None) -> None:
        for item in group:
            item.setChecked(item is button)
        if callback:
            callback()

    def _region_changed(self) -> None:
        self.force_refresh()

    def _rank_changed(self) -> None:
        self.force_refresh()

    def _category_changed(self) -> None:
        self.force_refresh()



class FavoritesPage(SelectionLibraryPage):
    """当前登录用户的商品快照收藏。"""

    def __init__(self, gateway: DataGateway) -> None:
        super().__init__(gateway)
        self.report_panel.hide()
        for label in self.findChildren(QLabel):
            if label.text() == "选品库":
                label.setText("采集箱")
            elif label.text() == "查看当前账号最近 7 天的 AI 搜索选品结果":
                label.setText("查看当前账号收藏的商品快照")
            elif label.text() == "我的搜索选品":
                label.setText("采集商品")

    def activate(self) -> None:
        self.load_favorites()
        self.refresh()
        self.loaded = True

    def refresh(self) -> None:
        while self.product_grid.count():
            child = self.product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._update_library_category_state(self.favorite_items)
        items = [item for item in self.favorite_items if self._matches_library_filter(item)]
        if not items:
            empty = QLabel("暂无采集商品，请在商品报告面板点击加入采集箱。")
            empty.setObjectName("Muted")
            self.product_grid.addWidget(empty, 0, 0)
            return
        listing = QTableWidget(0, 8)
        listing.setObjectName("CollectionTable")
        listing.setHorizontalHeaderLabels(["商品信息", "来源", "国家/地区", "商品分类", "价格", "销量", "1688 链接", "操作"])
        listing.verticalHeader().setVisible(False)
        listing.setShowGrid(False)
        listing.setAlternatingRowColors(True)
        listing.setSelectionBehavior(QAbstractItemView.SelectRows)
        listing.setSelectionMode(QAbstractItemView.NoSelection)
        listing.setEditTriggers(QAbstractItemView.NoEditTriggers)
        listing.setWordWrap(False)
        listing.setFocusPolicy(Qt.NoFocus)
        header = listing.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 310)
        for column in range(1, 8):
            header.setSectionResizeMode(column, QHeaderView.Stretch)

        for row, item in enumerate(items):
            listing.insertRow(row)
            snapshot = item.get("product_snapshot") if isinstance(item.get("product_snapshot"), dict) else {}
            supplier_raw = snapshot.get("supplier_raw_data") or snapshot.get("raw_data") or {}
            if isinstance(supplier_raw, str):
                try:
                    supplier_raw = json.loads(supplier_raw)
                except (TypeError, ValueError):
                    supplier_raw = {}
            if not isinstance(supplier_raw, dict):
                supplier_raw = {}
            title = str(item.get("title") or snapshot.get("title") or "未命名商品")
            image_url = str(item.get("image_url") or snapshot.get("supplier_image_url") or "")
            region = str(item.get("region") or snapshot.get("region") or snapshot.get("country") or "日本")
            category = str(
                item.get("supplier_category")
                or snapshot.get("supplier_category")
                or supplier_raw.get("category")
                or supplier_raw.get("category_name")
                or item.get("category")
                or snapshot.get("category")
                or "未分类"
            )
            price = item.get("price") or snapshot.get("supplier_price") or snapshot.get("suggested_price_min") or 0
            currency = str(item.get("currency") or snapshot.get("currency") or "JPY").upper()
            sales = item.get("sales_count") or snapshot.get("supplier_sales_count") or snapshot.get("sales_count") or 0
            source_url = str(
                item.get("supplier_source_url")
                or snapshot.get("supplier_source_url")
                or snapshot.get("source_url")
                or snapshot.get("detail_url")
                or ""
            )

            info = QWidget()
            info_layout = QHBoxLayout(info)
            info_layout.setContentsMargins(8, 5, 8, 5)
            info_layout.setSpacing(10)
            info_layout.addWidget(create_product_image(image_url, "📦", 66, 66), 0)
            title_label = QLabel(title[:24])
            title_label.setObjectName("CollectionTitle")
            title_label.setToolTip(title)
            title_label.setWordWrap(False)
            info_layout.addWidget(title_label, 1)
            listing.setCellWidget(row, 0, info)

            source_label = QLabel(product_source_label(item))
            source_label.setObjectName("CollectionText")
            source_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 1, source_label)

            for column, value in ((2, region), (3, category)):
                label = QLabel(value)
                label.setObjectName("CollectionText")
                label.setAlignment(Qt.AlignCenter)
                listing.setCellWidget(row, column, label)

            price_label = QLabel(format_region_price(region, price, currency))
            price_label.setObjectName("CollectionPrice")
            price_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 4, price_label)
            sales_label = QLabel(f"{int(float(sales or 0)):,}")
            sales_label.setObjectName("CollectionText")
            sales_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 5, sales_label)

            if source_url:
                listing.setCellWidget(row, 6, external_link_button("打开链接", source_url, self))
            else:
                no_link_label = QLabel("暂无链接")
                no_link_label.setObjectName("CollectionText")
                no_link_label.setAlignment(Qt.AlignCenter)
                listing.setCellWidget(row, 6, no_link_label)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)
            publish_button = QPushButton("加入上品")
            publish_button.setObjectName("CollectionAction")
            publish_button.clicked.connect(lambda checked=False, selected=item, url=source_url: self.add_to_publish(selected, url))
            detail_button = QPushButton("查看详情")
            detail_button.setObjectName("CollectionAction")
            detail_button.clicked.connect(lambda checked=False, selected=item: self.show_collection_detail(selected))
            actions_layout.addWidget(publish_button)
            actions_layout.addWidget(detail_button)
            listing.setCellWidget(row, 7, actions)
            listing.setRowHeight(row, 82)

        self.product_grid.addWidget(listing, 0, 0)
        if items:
            self._show_report(items[0])

    def add_to_publish(self, item: dict[str, Any], source_url: str) -> None:
        if not source_url:
            QMessageBox.information(self, "无法加入上品", "该商品没有可用的 1688 链接。")
            return
        main_window = self.window()
        if not hasattr(main_window, "nav") or not hasattr(main_window, "pages"):
            QMessageBox.information(self, "无法加入上品", "店铺管理页面暂不可用。")
            return
        for index in range(main_window.nav.count()):
            nav_item = main_window.nav.item(index)
            if nav_item and nav_item.text() == "店铺管理":
                main_window.nav.setCurrentRow(index)
                page_index = nav_item.data(Qt.UserRole)
                if isinstance(page_index, int) and 0 <= page_index < len(main_window.pages):
                    page = main_window.pages[page_index]
                    if hasattr(page, "offer_url_input"):
                        page.offer_url_input.setText(source_url)
                return
        QMessageBox.information(self, "无法加入上品", "未找到店铺管理页面。")

    def show_collection_detail(self, item: dict[str, Any]) -> None:
        """展示采集商品快照，避免把收藏商品重新绑定到会变化的业务记录。"""
        title = str(item.get("title") or item.get("derived_title") or "未命名商品")
        snapshot = item.get("product_snapshot") if isinstance(item.get("product_snapshot"), dict) else {}
        supplier_raw = snapshot.get("supplier_raw_data") or snapshot.get("raw_data") or {}
        if isinstance(supplier_raw, str):
            try:
                supplier_raw = json.loads(supplier_raw)
            except (TypeError, ValueError):
                supplier_raw = {}
        if not isinstance(supplier_raw, dict):
            supplier_raw = {}
        image_url = str(item.get("image_url") or snapshot.get("supplier_image_url") or "")
        price = item.get("price") or snapshot.get("supplier_price") or snapshot.get("suggested_price_min") or 0
        currency = str(item.get("currency") or snapshot.get("currency") or "JPY").upper()
        sales = item.get("sales_count") or snapshot.get("supplier_sales_count") or snapshot.get("sales_count") or 0
        region = str(item.get("region") or snapshot.get("region") or snapshot.get("country") or "日本")
        price_text = format_region_price(region, price, currency)
        category = str(item.get("category") or snapshot.get("category") or "未分类")
        source_url = str(item.get("supplier_source_url") or snapshot.get("supplier_source_url") or snapshot.get("source_url") or snapshot.get("detail_url") or "")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"商品详情 - {title[:36]}")
        dialog.resize(760, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QFrame()
        top.setObjectName("Card")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 12, 12, 12)
        top_layout.setSpacing(16)
        top_layout.addWidget(create_product_image(image_url, "📦", 180, 150), 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        title_label.setWordWrap(True)
        info.addWidget(title_label)
        price_label = QLabel(price_text)
        price_label.setObjectName("CollectionPrice")
        info.addWidget(price_label)
        facts = QLabel(f"国家/地区：{region}    商品分类：{category}\n销量：{int(float(sales or 0)):,}")
        facts.setObjectName("CollectionText")
        facts.setWordWrap(True)
        info.addWidget(facts)
        if source_url:
            info.addWidget(external_link_button("打开 1688 商品链接", source_url, self))
        else:
            info.addWidget(QLabel("暂无 1688 商品链接"))
        info.addStretch()
        top_layout.addLayout(info, 1)
        layout.addWidget(top)

        report_title = QLabel("选品分析报告")
        report_title.setObjectName("StudioPanelTitle")
        layout.addWidget(report_title)
        report_scroll = QScrollArea()
        report_scroll.setObjectName("StudioScroll")
        report_scroll.setWidgetResizable(True)
        report_content = QWidget()
        report_layout = QVBoxLayout(report_content)
        report_layout.setContentsMargins(0, 0, 4, 0)
        report_layout.setSpacing(6)
        dimensions = dimension_items_from_report(item)
        has_report = any(bool(level.strip() or detail.strip()) for _, level, detail in dimensions)
        if has_report:
            table = QFrame()
            table.setObjectName("StudioDimensionTable")
            table_layout = QVBoxLayout(table)
            table_layout.setContentsMargins(0, 0, 0, 0)
            table_layout.setSpacing(0)
            icons = ["◎", "≡", "↗", "◉", "◌", "▣", "♺", "△"]
            for index, (name, level, detail) in enumerate(dimensions):
                row = QFrame()
                row.setObjectName("StudioDimensionRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(8, 8, 8, 8)
                row_layout.setSpacing(8)
                icon = QLabel(icons[index % len(icons)])
                icon.setObjectName("StudioDimensionIcon")
                icon.setFixedSize(28, 28)
                icon.setAlignment(Qt.AlignCenter)
                row_layout.addWidget(icon, 0, Qt.AlignTop)
                copy = QVBoxLayout()
                copy.setSpacing(2)
                name_label = QLabel(name)
                name_label.setObjectName("StudioDimensionName")
                detail_label = QLabel(detail or "暂无分析内容")
                detail_label.setObjectName("StudioDimensionText")
                detail_label.setWordWrap(True)
                copy.addWidget(name_label)
                copy.addWidget(detail_label)
                row_layout.addLayout(copy, 1)
                grade = QLabel(level or "参考")
                grade.setObjectName("StudioDimensionGrade")
                row_layout.addWidget(grade, 0, Qt.AlignTop)
                table_layout.addWidget(row)
            report_layout.addWidget(table)
        else:
            empty_report = QLabel("暂无选品分析报告")
            empty_report.setObjectName("Muted")
            report_layout.addWidget(empty_report)
        report_layout.addStretch()
        report_scroll.setWidget(report_content)
        layout.addWidget(report_scroll, 1)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        dialog.exec()


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
        self.send_button = QPushButton("开始选品 10积分")
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
        self.report_panel.setFixedWidth(380)
        report_layout = QVBoxLayout(self.report_panel)
        report_layout.setContentsMargins(16, 16, 16, 16)
        report_layout.setSpacing(10)
        report_title = QLabel("选品分析报告")
        report_title.setObjectName("StudioPanelTitle")
        report_layout.addWidget(report_title)
        report_tabs = QHBoxLayout()
        report_tabs.setSpacing(4)
        self.report_tab_buttons: list[QPushButton] = []
        for tab_name in ("选品分析 1-6", "选品分析 7-8"):
            tab = QPushButton(tab_name)
            tab.setObjectName("StudioReportTab")
            tab.setCheckable(True)
            tab.setChecked(tab_name == "选品分析 1-6")
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
        workspace.addWidget(self.report_panel)
        self.layout.addLayout(workspace, 1)
        self.report_item: dict[str, Any] | None = None
        self.report_tab = "选品分析 1-6"
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

    def load_favorites(self) -> None:
        try:
            self.favorite_items = self.gateway.favorites()
        except Exception as exc:
            self.favorite_items = []
            parent = self.window()
            if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()

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
            if "积分不足" in str(exc):
                show_credit_recharge_prompt(self)
            else:
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
            detail = str(status.get("error_message") or "任务执行失败")
            QMessageBox.warning(
                self,
                "选品失败",
                f"选品失败，积分已按后端结果处理。\n\n{detail}",
            )

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
        self.report_product.setText(f"{title[:32]}\n{format_region_price(item.get('region'), price, item.get('currency'))}")
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(report_summary_markup(sales, score))
        image = create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140)
        self.report_image_layout.addWidget(image)
        dimensions = dimension_items_from_report(item)
        dimensions = dimensions[:6] if self.report_tab == "选品分析 1-6" else dimensions[6:8]
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
    def __init__(self, product: dict[str, Any], on_open, can_derive: bool = True, on_collect=None) -> None:
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
        price_label = QLabel(format_region_price(product.get("region"), price, product.get("currency")))
        price_label.setObjectName("ProductPrice")
        sales_label = QLabel(f"销量 {sales:,} 个")
        sales_label.setObjectName("ProductMuted")
        metrics.addWidget(price_label)
        metrics.addStretch()
        metrics.addWidget(sales_label)
        layout.addLayout(metrics)

        has_derived = int(product.get("derived_count") or 0) > 0
        if has_derived:
            open_button = QPushButton("查看衍生品")
            open_button.setObjectName("ProductDeriveView")
        elif can_derive:
            open_button = QPushButton("可以衍生")
            open_button.setObjectName("ProductDeriveAvailable")
        else:
            open_button = QPushButton("暂不支持衍生")
            open_button.setObjectName("ProductDeriveDisabled")
            open_button.setEnabled(False)
        if has_derived or can_derive:
            open_button.clicked.connect(lambda: self.on_open(self.product))
        if on_collect:
            open_button.setMinimumWidth(0)
            open_button.setMinimumHeight(30)
            open_button.setMaximumHeight(32)
            open_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            action_row = QHBoxLayout()
            action_row.setSpacing(6)
            action_row.addWidget(open_button, 1)
            collect_button = QPushButton("加入选品库")
            collect_button.setObjectName("ProductCollect")
            collect_button.setMinimumHeight(30)
            collect_button.setMaximumHeight(32)
            collect_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            collect_button.clicked.connect(lambda checked=False, button=collect_button: on_collect(self.product, button))
            action_row.addWidget(collect_button, 1)
            layout.addLayout(action_row)
        else:
            open_button.setMinimumWidth(130)
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


AUTO_PUBLISH_LINK_LIMIT = 10


class AutoPublishOfferRow(QFrame):
    def __init__(self, offer_url: str, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.offer_url = offer_url
        self.setObjectName("AutoPublishOfferCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(88)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        index_label = QLabel(f"{index:02d}")
        index_label.setObjectName("AutoPublishIndex")
        index_label.setAlignment(Qt.AlignCenter)
        index_label.setFixedSize(32, 32)

        url_box = QVBoxLayout()
        url_box.setSpacing(4)
        url_title = QLabel("1688 链接")
        url_title.setObjectName("AutoPublishHint")
        self.url_label = QLabel(offer_url)
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.setWordWrap(True)
        self.url_label.setObjectName("AutoPublishUrl")
        url_box.addWidget(url_title)
        url_box.addWidget(self.url_label)
        layout.addWidget(index_label)
        layout.addLayout(url_box, 1)

        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(1, 100000)
        self.weight_spin.setSuffix(" g")
        self.weight_spin.setValue(500)
        self.weight_spin.setFixedSize(78, 30)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 1000)
        self.length_spin.setSuffix(" cm")
        self.length_spin.setValue(10)
        self.length_spin.setFixedSize(72, 30)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1000)
        self.width_spin.setSuffix(" cm")
        self.width_spin.setValue(10)
        self.width_spin.setFixedSize(72, 30)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 1000)
        self.height_spin.setSuffix(" cm")
        self.height_spin.setValue(40)
        self.height_spin.setFixedSize(72, 30)

        def make_field(title: str, widget: QWidget) -> QFrame:
            field = QFrame()
            field.setObjectName("AutoPublishSpecBox")
            field.setFixedWidth(92 if title == "重量" else 88)
            field.setFixedHeight(58)
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(6, 4, 6, 4)
            field_layout.setSpacing(2)
            label = QLabel(title)
            label.setObjectName("AutoPublishHint")
            field_layout.addWidget(label)
            field_layout.addWidget(widget)
            return field

        spec_row = QHBoxLayout()
        spec_row.setSpacing(8)
        spec_row.addWidget(make_field("重量", self.weight_spin))
        spec_row.addWidget(make_field("长", self.length_spin))
        spec_row.addWidget(make_field("宽", self.width_spin))
        spec_row.addWidget(make_field("高", self.height_spin))
        layout.addLayout(spec_row)
        self.setLayout(layout)

    def collect_payload(self) -> dict[str, Any]:
        return {
            "offer_url": self.offer_url,
            "package_weight_g": int(self.weight_spin.value()),
            "package_length_cm": int(self.length_spin.value()),
            "package_width_cm": int(self.width_spin.value()),
            "package_height_cm": int(self.height_spin.value()),
        }

    def restore_from(self, values: dict[str, Any]) -> None:
        if not isinstance(values, dict):
            return
        for key, spinbox in (
            ("package_weight_g", self.weight_spin),
            ("package_length_cm", self.length_spin),
            ("package_width_cm", self.width_spin),
            ("package_height_cm", self.height_spin),
        ):
            value = values.get(key)
            if isinstance(value, (int, float)):
                spinbox.setValue(int(value))
            elif isinstance(value, str) and value.strip().isdigit():
                spinbox.setValue(int(value.strip()))


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
                    "items": [
                        {
                            "offer_url": str(payload.get("offer_url") or ""),
                            "package_weight_g": int(payload.get("package_weight_g") or 500),
                            "package_length_cm": int(payload.get("package_length_cm") or 10),
                            "package_width_cm": int(payload.get("package_width_cm") or 10),
                            "package_height_cm": int(payload.get("package_height_cm") or 40),
                            "profit_rule": str(payload.get("profit_rule") or ""),
                            "pricing_currency": str(payload.get("pricing_currency") or "CNY"),
                        }
                        for payload in self.payloads
                    ],
                    "publish_count": len(self.payloads),
                    "target_channel": first_payload.get("target_channel") or "TikTok Shop Japan",
                    "target_language": first_payload.get("target_language") or "ja",
                    "erp_url": first_payload.get("erp_url") or "https://erp.91miaoshou.com/?ac=1og270",
                    "dry_run": bool(first_payload.get("dry_run")),
                    "enable_image_translation": bool(first_payload.get("enable_image_translation", True)),
                    "enable_image_removal": bool(first_payload.get("enable_image_removal", True)),
                    "enable_title_optimization": bool(first_payload.get("enable_title_optimization", True)),
                    "enable_sku_optimization": bool(first_payload.get("enable_sku_optimization", True)),
                    "enable_description_optimization": bool(first_payload.get("enable_description_optimization", True)),
                    "remove_logo": bool(first_payload.get("remove_logo", True)),
                    "remove_transparent_text": bool(first_payload.get("remove_transparent_text", True)),
                    "remove_text": bool(first_payload.get("remove_text", False)),
                    "remove_psoriasis": bool(first_payload.get("remove_psoriasis", True)),
                    "profit_rule": str(first_payload.get("profit_rule") or ""),
                    "pricing_currency": str(first_payload.get("pricing_currency") or "CNY"),
                }
            )
            self.signals.created.emit(task)
            result = wait_for_auto_publish_result(self.gateway, str(task["task_id"]))
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class MiaoshouPictureSpaceAuthTask(QRunnable):
    def __init__(self, gateway: DataGateway, signals: AutoPublishSignals) -> None:
        super().__init__()
        self.gateway = gateway
        self.signals = signals

    @Slot()
    def run(self) -> None:
        browser = None
        context = None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self.signals.failed.emit(f"桌面端缺少 Playwright，无法打开妙手授权窗口：{exc}")
            return

        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, Any] = {"headless": False, "slow_mo": 80}
                for browser_path in DESKTOP_BROWSER_PATHS:
                    if browser_path.exists():
                        launch_options["executable_path"] = str(browser_path)
                        break
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.goto("https://erp.91miaoshou.com/?ac=1og270", wait_until="domcontentloaded", timeout=60000)
                deadline = time.time() + 600
                last_url = ""
                while time.time() < deadline:
                    page.wait_for_timeout(1000)
                    try:
                        last_url = page.url
                        body_text = page.locator("body").inner_text(timeout=1200)
                    except Exception:
                        body_text = ""
                    cookies = context.cookies()
                    has_miaoshou_cookie = any("91miaoshou.com" in str(cookie.get("domain") or "") for cookie in cookies)
                    has_backend_text = bool(re.search(r"采集箱|图片空间|授权店铺|订单|商品|刊登|工作台", body_text))
                    still_login_page = bool(re.search(r"账号登录|扫码登录|立即登录|验证码登录|登录密码", body_text))
                    if has_miaoshou_cookie and has_backend_text and not still_login_page:
                        storage_state = context.storage_state()
                        result = self.gateway.reauthorize_miaoshou_picture_space({"storage_state": storage_state})
                        self.signals.finished.emit(result)
                        return
                raise TimeoutError(f"等待妙手登录超时。最后停留页面：{last_url or '未知'}")
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
            except Exception:
                pass


class AutoPublishPage(Page):
    def __init__(self, gateway: DataGateway) -> None:
        super().__init__()
        self.gateway = gateway
        self.loaded = False
        self.current_task: dict[str, Any] | None = None
        self.task_signals: AutoPublishSignals | None = None
        self.reauth_signals: AutoPublishSignals | None = None
        self.offer_meta_rows: list[AutoPublishOfferRow] = []
        self.miaoshou_shop_options: list[dict[str, Any]] = []
        self.offer_meta_sync_timer = QTimer(self)
        self.offer_meta_sync_timer.setSingleShot(True)
        self.offer_meta_sync_timer.setInterval(120)
        self.offer_meta_sync_timer.timeout.connect(self.sync_offer_meta_rows)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1500)
        self.progress_timer.timeout.connect(self.refresh_task_progress)
        self.progress_animation_timer = QTimer(self)
        self.progress_animation_timer.setInterval(80)
        self.progress_animation_timer.timeout.connect(self.animate_progress_bar)
        self.progress_target_value = 0

        root_layout = self.layout
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setObjectName("ProductScroll")
        self.page_content = QWidget()
        self.page_content.setObjectName("AutoPublishSection")
        self.layout = QVBoxLayout(self.page_content)
        self.layout.setContentsMargins(22, 20, 22, 20)
        self.layout.setSpacing(12)
        self.page_scroll.setWidget(self.page_content)
        root_layout.addWidget(self.page_scroll)

        self.layout.addWidget(
            make_title(
                "自动上架",
                "1688 链接进入妙手开放平台采集箱，标题、规格、产品描述、图片翻译与智能抹除均可按需勾选。",
            )
        )

        self.offer_url_input = QTextEdit()
        self.offer_url_input.setObjectName("AutoPublishInput")
        self.offer_url_input.setPlaceholderText(
            "粘贴 1688 商品链接，每行一个。\n也可以只粘贴 offerId，例如 123456789012。"
        )
        self.offer_url_input.setFixedHeight(112)
        self.offer_url_input.textChanged.connect(self.schedule_offer_meta_sync)

        self.language_select = QComboBox()
        self.language_select.addItem("日语", "ja")
        self.language_select.addItem("英语", "en")
        self.language_select.currentIndexChanged.connect(self.update_summary_state)

        self.dry_run = QCheckBox("仅保存不发布")
        self.dry_run.setChecked(True)
        self.dry_run.toggled.connect(self.update_summary_state)

        self.listing_text_master_checkbox = QCheckBox("妙手文案")
        self.listing_text_master_checkbox.blockSignals(True)
        self.listing_text_master_checkbox.setChecked(True)
        self.listing_text_master_checkbox.blockSignals(False)
        self.listing_text_master_checkbox.toggled.connect(self.toggle_listing_text_group)
        self.listing_title_checkbox = QCheckBox("标题")
        self.listing_title_checkbox.blockSignals(True)
        self.listing_title_checkbox.setChecked(True)
        self.listing_title_checkbox.blockSignals(False)
        self.listing_title_checkbox.toggled.connect(self.sync_listing_text_master_state)
        self.listing_sku_checkbox = QCheckBox("规格")
        self.listing_sku_checkbox.blockSignals(True)
        self.listing_sku_checkbox.setChecked(True)
        self.listing_sku_checkbox.blockSignals(False)
        self.listing_sku_checkbox.toggled.connect(self.sync_listing_text_master_state)
        self.listing_description_checkbox = QCheckBox("产品描述")
        self.listing_description_checkbox.blockSignals(True)
        self.listing_description_checkbox.setChecked(True)
        self.listing_description_checkbox.blockSignals(False)
        self.listing_description_checkbox.toggled.connect(self.sync_listing_text_master_state)

        self.image_translation_checkbox = QCheckBox("图片翻译")
        self.image_translation_checkbox.blockSignals(True)
        self.image_translation_checkbox.setChecked(True)
        self.image_translation_checkbox.blockSignals(False)
        self.image_translation_checkbox.toggled.connect(self.update_summary_state)
        self.image_removal_master_checkbox = QCheckBox("智能抹除")
        self.image_removal_master_checkbox.blockSignals(True)
        self.image_removal_master_checkbox.setChecked(True)
        self.image_removal_master_checkbox.blockSignals(False)
        self.image_removal_master_checkbox.toggled.connect(self.toggle_image_removal_group)
        self.remove_logo_checkbox = QCheckBox("去除LOGO")
        self.remove_logo_checkbox.blockSignals(True)
        self.remove_logo_checkbox.setChecked(True)
        self.remove_logo_checkbox.blockSignals(False)
        self.remove_logo_checkbox.toggled.connect(self.sync_image_removal_master_state)
        self.remove_transparent_text_checkbox = QCheckBox("去除透明字块")
        self.remove_transparent_text_checkbox.blockSignals(True)
        self.remove_transparent_text_checkbox.setChecked(True)
        self.remove_transparent_text_checkbox.blockSignals(False)
        self.remove_transparent_text_checkbox.toggled.connect(self.sync_image_removal_master_state)
        self.remove_text_checkbox = QCheckBox("去除文字")
        self.remove_text_checkbox.blockSignals(True)
        self.remove_text_checkbox.setChecked(False)
        self.remove_text_checkbox.blockSignals(False)
        self.remove_text_checkbox.toggled.connect(self.sync_image_removal_master_state)
        self.remove_psoriasis_checkbox = QCheckBox("去除牛皮癣")
        self.remove_psoriasis_checkbox.blockSignals(True)
        self.remove_psoriasis_checkbox.setChecked(True)
        self.remove_psoriasis_checkbox.blockSignals(False)
        self.remove_psoriasis_checkbox.toggled.connect(self.sync_image_removal_master_state)

        self.listing_text_controls = [
            self.listing_title_checkbox,
            self.listing_sku_checkbox,
            self.listing_description_checkbox,
        ]
        self.image_removal_controls = [
            self.remove_logo_checkbox,
            self.remove_transparent_text_checkbox,
            self.remove_text_checkbox,
            self.remove_psoriasis_checkbox,
        ]

        self.miaoshou_shop_combo = QComboBox()
        self.miaoshou_shop_combo.setObjectName("AutoPublishShopCombo")
        self.miaoshou_shop_combo.setMinimumHeight(30)
        self.miaoshou_shop_combo.setMinimumWidth(180)
        self.miaoshou_shop_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.miaoshou_shop_combo.currentIndexChanged.connect(self.update_summary_state)
        self.miaoshou_app_key_input = QLineEdit()
        self.miaoshou_app_key_input.setObjectName("AutoPublishMiaoshouAppKey")
        self.miaoshou_app_key_input.setPlaceholderText("填写妙手 AppKey")
        self.miaoshou_app_key_input.setMinimumHeight(30)
        self.miaoshou_app_key_input.setMinimumWidth(180)
        self.miaoshou_app_secret_input = QLineEdit()
        self.miaoshou_app_secret_input.setObjectName("AutoPublishMiaoshouAppSecret")
        self.miaoshou_app_secret_input.setPlaceholderText("填写妙手 AppSecret")
        self.miaoshou_app_secret_input.setMinimumHeight(30)
        self.miaoshou_app_secret_input.setMinimumWidth(180)
        self.miaoshou_app_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.miaoshou_api_base_url_input = QLineEdit()
        self.miaoshou_api_base_url_input.setObjectName("AutoPublishMiaoshouApiBaseUrl")
        self.miaoshou_api_base_url_input.setPlaceholderText("https://openapi-erp.91miaoshou.com")
        self.miaoshou_api_base_url_input.setText("https://openapi-erp.91miaoshou.com")
        self.miaoshou_api_base_url_input.setMinimumHeight(30)
        self.miaoshou_api_base_url_input.setMinimumWidth(260)
        self.miaoshou_shop_refresh_button = QPushButton("刷新店铺")
        self.miaoshou_shop_refresh_button.setObjectName("AutoPublishShopRefresh")
        self.miaoshou_shop_refresh_button.setFixedSize(76, 30)
        self.miaoshou_shop_refresh_button.clicked.connect(self.refresh_miaoshou_shop_options)
        self.miaoshou_reauth_button = QPushButton("图片空间授权")
        self.miaoshou_reauth_button.setObjectName("AutoPublishReauth")
        self.miaoshou_reauth_button.setFixedSize(104, 30)
        self.miaoshou_reauth_button.clicked.connect(self.reauthorize_miaoshou_picture_space)
        self.profit_rule_input = QLineEdit()
        self.profit_rule_input.setObjectName("AutoPublishProfitInput")
        self.profit_rule_input.setPlaceholderText("20 或 20%")
        self.profit_rule_input.setFixedSize(86, 30)
        self.profit_rule_input.textChanged.connect(self.update_summary_state)
        self.refresh_button = QPushButton("重置")
        self.refresh_button.setObjectName("AutoPublishSecondaryAction")
        self.refresh_button.setFixedSize(66, 30)
        self.create_button = QPushButton("开始上架")
        self.create_button.setObjectName("AutoPublishPrimaryAction")
        self.create_button.setFixedSize(96, 30)
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button.clicked.connect(self.create_1688_task)

        self.offer_meta_scroll = QScrollArea()
        self.offer_meta_scroll.setWidgetResizable(True)
        self.offer_meta_scroll.setFixedHeight(198)
        self.offer_meta_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.offer_meta_content = QWidget()
        self.offer_meta_layout = QVBoxLayout(self.offer_meta_content)
        self.offer_meta_layout.setContentsMargins(0, 0, 0, 0)
        self.offer_meta_layout.setSpacing(8)
        meta_empty = QLabel("识别到链接后，这里会出现每个商品的重量和尺寸。默认 500g / 10 x 10 x 40cm。")
        meta_empty.setObjectName("AutoPublishHint")
        meta_empty.setWordWrap(True)
        self.offer_meta_layout.addWidget(meta_empty)
        self.offer_meta_layout.addStretch(1)
        self.offer_meta_scroll.setWidget(self.offer_meta_content)

        workspace = QFrame()
        workspace.setObjectName("AutoPublishCard")
        workspace_layout = QGridLayout(workspace)
        workspace_layout.setContentsMargins(18, 16, 18, 16)
        workspace_layout.setHorizontalSpacing(18)
        workspace_layout.setVerticalSpacing(12)
        workspace_layout.setColumnStretch(0, 1)

        source_title = QLabel("1688 商品链接")
        source_title.setObjectName("CardTitle")
        self.link_count_label = QLabel("0 条")
        self.link_count_label.setObjectName("AutoPublishPill")
        source_head = QHBoxLayout()
        source_head.addWidget(source_title)
        source_head.addStretch()
        source_head.addWidget(self.link_count_label)
        workspace_layout.addLayout(source_head, 0, 0)
        workspace_layout.addWidget(self.offer_url_input, 1, 0)

        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        api_label = QLabel("妙手 API")
        api_label.setObjectName("AutoPublishHint")
        api_row.addWidget(api_label)
        api_row.addWidget(self.miaoshou_app_key_input)
        api_row.addWidget(self.miaoshou_app_secret_input)
        api_row.addWidget(self.miaoshou_api_base_url_input)
        api_row.addStretch(1)
        workspace_layout.addLayout(api_row, 2, 0)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.dry_run)
        action_row.addWidget(self.image_translation_checkbox)
        action_row.addStretch(1)
        profit_label = QLabel("目标利润")
        profit_label.setObjectName("AutoPublishHint")
        action_row.addWidget(profit_label)
        action_row.addWidget(self.profit_rule_input)
        shop_label = QLabel("目标店铺")
        shop_label.setObjectName("AutoPublishHint")
        action_row.addWidget(shop_label)
        action_row.addWidget(self.miaoshou_shop_combo)
        action_row.addWidget(self.miaoshou_shop_refresh_button)
        action_row.addWidget(self.miaoshou_reauth_button)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.create_button)
        workspace_layout.addLayout(action_row, 3, 0)

        listing_row = QHBoxLayout()
        listing_row.setSpacing(8)
        listing_label = QLabel("文案处理")
        listing_label.setObjectName("AutoPublishHint")
        listing_row.addWidget(listing_label)
        listing_row.addWidget(self.listing_text_master_checkbox)
        listing_row.addWidget(self.listing_title_checkbox)
        listing_row.addWidget(self.listing_sku_checkbox)
        listing_row.addWidget(self.listing_description_checkbox)
        listing_row.addStretch(1)
        workspace_layout.addLayout(listing_row, 4, 0)

        removal_row = QHBoxLayout()
        removal_row.setSpacing(8)
        removal_label = QLabel("智能抹除")
        removal_label.setObjectName("AutoPublishHint")
        removal_row.addWidget(removal_label)
        removal_row.addWidget(self.image_removal_master_checkbox)
        removal_row.addWidget(self.remove_logo_checkbox)
        removal_row.addWidget(self.remove_transparent_text_checkbox)
        removal_row.addWidget(self.remove_text_checkbox)
        removal_row.addWidget(self.remove_psoriasis_checkbox)
        removal_row.addStretch(1)
        workspace_layout.addLayout(removal_row, 5, 0)

        self.shop_info_label = QLabel("店铺信息：请先在上方填写妙手 AppKey / AppSecret，再刷新店铺。")
        self.shop_info_label.setObjectName("AutoPublishShopInfo")
        self.shop_info_label.setWordWrap(True)
        workspace_layout.addWidget(self.shop_info_label, 6, 0)

        meta_title = QLabel("重量与尺寸")
        meta_title.setObjectName("CardTitle")
        workspace_layout.addWidget(meta_title, 7, 0)
        workspace_layout.addWidget(self.offer_meta_scroll, 8, 0)
        self.layout.addWidget(workspace)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        progress_card = QFrame()
        progress_card.setObjectName("AutoPublishCard")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 12, 16, 12)
        progress_layout.setSpacing(8)
        progress_head = QHBoxLayout()
        progress_title = QLabel("任务进度")
        progress_title.setObjectName("CardTitle")
        self.progress_phase = QLabel("待开始")
        self.progress_phase.setObjectName("AutoPublishPill")
        progress_head.addWidget(progress_title)
        progress_head.addStretch()
        progress_head.addWidget(self.progress_phase)
        progress_layout.addLayout(progress_head)
        self.progress_label = QLabel("输入 1688 链接后点击开始执行。")
        self.progress_label.setObjectName("AutoPublishHint")
        self.progress_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        status_row.addWidget(progress_card, 1)

        usage_card = QFrame()
        usage_card.setObjectName("AutoPublishCard")
        usage_layout = QVBoxLayout(usage_card)
        usage_layout.setContentsMargins(16, 12, 16, 12)
        usage_layout.setSpacing(8)
        usage_head = QHBoxLayout()
        usage_title = QLabel("API 用量统计")
        usage_title.setObjectName("CardTitle")
        usage_head.addWidget(usage_title)
        usage_head.addStretch()
        self.api_usage_summary = QLabel("等待任务完成后显示调用次数、图片数量和 Token 用量。")
        self.api_usage_summary.setObjectName("AutoPublishHint")
        self.api_usage_summary.setWordWrap(True)
        self.api_usage_detail = QLabel("暂无数据")
        self.api_usage_detail.setObjectName("ProductMuted")
        self.api_usage_detail.setWordWrap(True)
        usage_layout.addLayout(usage_head)
        usage_layout.addWidget(self.api_usage_summary)
        usage_layout.addWidget(self.api_usage_detail)
        status_row.addWidget(usage_card, 1)
        self.layout.addLayout(status_row)

        result_card = QFrame()
        result_card.setObjectName("AutoPublishCard")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(16, 12, 16, 12)
        result_layout.setSpacing(8)
        result_title = QLabel("执行结果")
        result_title.setObjectName("CardTitle")
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(170)
        self.result.setPlaceholderText("任务执行结果会显示在这里。")
        result_layout.addWidget(result_title)
        result_layout.addWidget(self.result)
        self.layout.addWidget(result_card, 1)
        self.update_summary_state()
        self.refresh_miaoshou_shop_options(silent=True)

    def activate(self) -> None:
        if not self.loaded:
            self.result.setPlaceholderText("粘贴 1688 商品链接后点击开始上架。长任务会在后台执行，窗口不会卡住。")
            self.loaded = True
        self.update_summary_state()
        if not self.miaoshou_shop_options:
            self.refresh_miaoshou_shop_options(silent=True)

    def refresh(self) -> None:
        self.current_task = None
        self.progress_timer.stop()
        self.reset_flow()
        self.result.clear()
        self.update_miaoshou_shop_summary()
        self.update_summary_state()

    def update_summary_state(self, *_args: Any) -> None:
        offer_count = len(self.extract_offer_urls(self.offer_url_input.toPlainText()))
        self.link_count_label.setText(f"{offer_count} 条")
        self.update_miaoshou_shop_summary()

    def current_shop_option(self) -> dict[str, Any] | None:
        index = self.miaoshou_shop_combo.currentIndex()
        if index < 0:
            return None
        data = self.miaoshou_shop_combo.currentData()
        if isinstance(data, dict):
            return data
        return None

    def current_shop_id(self) -> int | None:
        option = self.current_shop_option()
        if not option:
            return None
        shop_id = option.get("shop_id")
        if isinstance(shop_id, int):
            return shop_id
        if isinstance(shop_id, str) and shop_id.isdigit():
            return int(shop_id)
        return None

    def current_shop_label(self) -> str:
        option = self.current_shop_option()
        if not option:
            return "未选择店铺"
        shop_name = str(option.get("shop_name") or "").strip()
        shop_id = option.get("shop_id")
        if shop_name and shop_id is not None:
            return f"{shop_name}（{shop_id}）"
        if shop_name:
            return shop_name
        if shop_id is not None:
            return f"店铺ID {shop_id}"
        return "未命名店铺"

    def toggle_listing_text_group(self, checked: bool) -> None:
        for control in self.listing_text_controls:
            control.blockSignals(True)
            control.setChecked(checked)
            control.blockSignals(False)
        self.update_summary_state()

    def sync_listing_text_master_state(self, *_args: Any) -> None:
        all_checked = all(control.isChecked() for control in self.listing_text_controls)
        self.listing_text_master_checkbox.blockSignals(True)
        self.listing_text_master_checkbox.setChecked(all_checked)
        self.listing_text_master_checkbox.blockSignals(False)
        self.update_summary_state()

    def toggle_image_removal_group(self, checked: bool) -> None:
        for control in self.image_removal_controls:
            control.blockSignals(True)
            control.setChecked(checked)
            control.blockSignals(False)
        self.update_summary_state()

    def sync_image_removal_master_state(self, *_args: Any) -> None:
        all_checked = all(control.isChecked() for control in self.image_removal_controls)
        self.image_removal_master_checkbox.blockSignals(True)
        self.image_removal_master_checkbox.setChecked(all_checked)
        self.image_removal_master_checkbox.blockSignals(False)
        self.update_summary_state()

    def image_translation_enabled(self) -> bool:
        return self.image_translation_checkbox.isChecked()

    def image_removal_enabled(self) -> bool:
        return self.image_removal_master_checkbox.isChecked()

    def listing_title_enabled(self) -> bool:
        return self.listing_title_checkbox.isChecked()

    def listing_sku_enabled(self) -> bool:
        return self.listing_sku_checkbox.isChecked()

    def listing_description_enabled(self) -> bool:
        return self.listing_description_checkbox.isChecked()

    def smart_removal_remove_logo_enabled(self) -> bool:
        return self.remove_logo_checkbox.isChecked()

    def smart_removal_remove_transparent_text_enabled(self) -> bool:
        return self.remove_transparent_text_checkbox.isChecked()

    def smart_removal_remove_text_enabled(self) -> bool:
        return self.remove_text_checkbox.isChecked()

    def smart_removal_remove_psoriasis_enabled(self) -> bool:
        return self.remove_psoriasis_checkbox.isChecked()

    def update_miaoshou_shop_summary(self) -> None:
        count = len(self.miaoshou_shop_options)
        if count:
            self.shop_info_label.setText(f"店铺信息：已加载 {count} 个店铺，当前选择 {self.current_shop_label()}。")
            self.miaoshou_shop_combo.setEnabled(True)
        else:
            self.shop_info_label.setText("店铺信息：请先在页面顶部填写妙手 AppKey / AppSecret，再刷新店铺。")
            self.miaoshou_shop_combo.setEnabled(False)

    @staticmethod
    def _first_nonempty(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _miaoshou_sign(app_secret: str, path: str, timestamp: int, app_key: str, body_json: str) -> str:
        content = f"{app_secret}{path}{timestamp}{app_key}{body_json}{app_secret}"
        return hmac.new(app_secret.encode("utf-8"), content.encode("utf-8"), hashlib.sha256).hexdigest()

    def _collect_miaoshou_credentials_from_inputs(self) -> dict[str, str]:
        app_key = self._first_nonempty(self.miaoshou_app_key_input.text())
        app_secret = self._first_nonempty(self.miaoshou_app_secret_input.text())
        base_url = self._first_nonempty(self.miaoshou_api_base_url_input.text(), "https://openapi-erp.91miaoshou.com")
        if app_key and app_secret:
            return {
                "app_key": app_key,
                "app_secret": app_secret,
                "base_url": base_url.rstrip("/"),
            }
        return {}

    def _find_miaoshou_credentials(self) -> dict[str, str]:
        direct_credentials = self._collect_miaoshou_credentials_from_inputs()
        if direct_credentials:
            return direct_credentials
        for config in self.gateway.third_party_configs():
            if str(config.get("service_type") or "").strip() != "miaoshou_api":
                continue
            if int(config.get("status") or 0) != 1:
                continue
            app_key = self._first_nonempty(config.get("access_key_encrypted"))
            app_secret = self._first_nonempty(config.get("secret_key_encrypted"))
            base_url = self._first_nonempty(config.get("api_base_url"), "https://openapi-erp.91miaoshou.com")
            if app_key and app_secret:
                return {
                    "app_key": app_key,
                    "app_secret": app_secret,
                    "base_url": base_url.rstrip("/"),
                }
        return {}

    def _load_miaoshou_shop_options_direct(self, target_site: str = "JP") -> list[dict[str, Any]]:
        credentials = self._find_miaoshou_credentials()
        if not credentials:
            raise ApiError("请先在页面顶部填写妙手 AppKey / AppSecret。")
        path = "/open/v1/product/shop/shop/get_shop_list"
        payload = {"platform": "tiktok", "site": target_site, "pageNo": 1, "pageSize": 100}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        sign = self._miaoshou_sign(credentials["app_secret"], path, timestamp, credentials["app_key"], body)
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{credentials['base_url']}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-app-key": credentials["app_key"],
                "x-timestamp": str(timestamp),
                "x-sign": sign,
            },
            timeout=60,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError(f"妙手店铺接口返回了非 JSON 响应：{response.text[:200]}") from exc
        if response.status_code >= 400:
            message = ""
            if isinstance(data, dict):
                message = str(data.get("message") or data.get("msg") or "")
            raise ApiError(message or f"HTTP {response.status_code}: 拉取店铺失败")
        if not isinstance(data, dict) or str(data.get("result") or "").lower() not in {"success", "ok"}:
            message = ""
            if isinstance(data, dict):
                message = str(data.get("message") or data.get("msg") or data.get("code") or "")
            raise ApiError(message or "妙手店铺接口返回失败")
        shop_list = (((data.get("data") or {}) if isinstance(data, dict) else {}) or {}).get("shopList") if isinstance(data, dict) else []
        options: list[dict[str, Any]] = []
        if isinstance(shop_list, list):
            for shop in shop_list:
                if not isinstance(shop, dict):
                    continue
                if str(shop.get("platform") or "").lower() != "tiktok":
                    continue
                if target_site and str(shop.get("site") or "").upper() != target_site.upper():
                    continue
                shop_id = shop.get("shopId")
                if isinstance(shop_id, str) and shop_id.isdigit():
                    shop_id = int(shop_id)
                if not isinstance(shop_id, int):
                    continue
                options.append(
                    {
                        "shop_id": shop_id,
                        "shop_name": self._first_nonempty(
                            shop.get("shopName"),
                            shop.get("shop_name"),
                            shop.get("name"),
                            shop.get("nick"),
                            shop.get("storeName"),
                            shop.get("store_name"),
                            f"店铺 {shop_id}",
                        ),
                        "platform": str(shop.get("platform") or "tiktok"),
                        "site": str(shop.get("site") or target_site or ""),
                    }
                )

        shop_ids = [int(item["shop_id"]) for item in options if isinstance(item.get("shop_id"), int)]
        name_map: dict[int, str] = {}
        if shop_ids:
            warehouse_path = "/open/v1/product/collect_box/tiktok/collect_box/get_shop_warehouse_list"
            warehouse_payload = {"shopIds": shop_ids}
            warehouse_body = json.dumps(warehouse_payload, ensure_ascii=False, separators=(",", ":"))
            warehouse_timestamp = int(time.time())
            warehouse_sign = self._miaoshou_sign(
                credentials["app_secret"],
                warehouse_path,
                warehouse_timestamp,
                credentials["app_key"],
                warehouse_body,
            )
            warehouse_response = session.post(
                f"{credentials['base_url']}{warehouse_path}",
                data=warehouse_body,
                headers={
                    "Content-Type": "application/json",
                    "x-app-key": credentials["app_key"],
                    "x-timestamp": str(warehouse_timestamp),
                    "x-sign": warehouse_sign,
                },
                timeout=60,
            )
            try:
                warehouse_data = warehouse_response.json()
            except ValueError:
                warehouse_data = {}
            if (
                warehouse_response.status_code < 400
                and isinstance(warehouse_data, dict)
                and str(warehouse_data.get("result") or "").lower() in {"success", "ok"}
            ):
                warehouse_list = (((warehouse_data.get("data") or {}) if isinstance(warehouse_data, dict) else {}) or {}).get("shopWarehouseList")
                if isinstance(warehouse_list, list):
                    for warehouse in warehouse_list:
                        if not isinstance(warehouse, dict):
                            continue
                        shop_id = warehouse.get("shopId")
                        if isinstance(shop_id, str) and shop_id.isdigit():
                            shop_id = int(shop_id)
                        if not isinstance(shop_id, int):
                            continue
                        shop_name = self._first_nonempty(
                            warehouse.get("shopName"),
                            warehouse.get("shop_name"),
                            warehouse.get("name"),
                        )
                        if shop_name:
                            name_map[shop_id] = shop_name

        if name_map:
            for item in options:
                shop_id = item.get("shop_id")
                if not isinstance(shop_id, int):
                    continue
                current_name = self._first_nonempty(item.get("shop_name"))
                fallback_name = f"店铺 {shop_id}"
                mapped_name = name_map.get(shop_id, "")
                if not current_name or current_name == fallback_name:
                    item["shop_name"] = mapped_name or current_name or fallback_name

        deduped: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for item in options:
            shop_id = int(item["shop_id"])
            if shop_id in seen_ids:
                continue
            seen_ids.add(shop_id)
            deduped.append(item)
        return deduped

    def refresh_miaoshou_shop_options(self, silent: bool = False) -> None:
        self.miaoshou_shop_refresh_button.setEnabled(False)
        self.miaoshou_shop_refresh_button.setText("加载中...")
        try:
            options = self._load_miaoshou_shop_options_direct("JP")
        except Exception as exc:
            if not silent:
                parent = self.window()
                if self.gateway.is_invalid_token_error(exc) and hasattr(parent, "clear_invalid_session"):
                    parent.clear_invalid_session()
                QMessageBox.warning(self, "拉取店铺失败", str(exc))
            self.miaoshou_shop_options = []
            self.miaoshou_shop_combo.blockSignals(True)
            self.miaoshou_shop_combo.clear()
            self.miaoshou_shop_combo.blockSignals(False)
            self.update_miaoshou_shop_summary()
            return
        finally:
            self.miaoshou_shop_refresh_button.setEnabled(True)
            self.miaoshou_shop_refresh_button.setText("刷新店铺")
        previous_shop_id = self.current_shop_id()
        self.miaoshou_shop_options = options
        self.miaoshou_shop_combo.blockSignals(True)
        self.miaoshou_shop_combo.clear()
        for option in options:
            shop_id = option.get("shop_id")
            shop_name = str(option.get("shop_name") or "").strip()
            label = f"{shop_name}（{shop_id}）" if shop_name else f"店铺ID {shop_id}"
            self.miaoshou_shop_combo.addItem(label, option)
        if options:
            selected_index = 0
            if previous_shop_id is not None:
                for index, option in enumerate(options):
                    if int(option.get("shop_id") or 0) == int(previous_shop_id):
                        selected_index = index
                        break
            self.miaoshou_shop_combo.setCurrentIndex(selected_index)
        self.miaoshou_shop_combo.blockSignals(False)
        self.update_miaoshou_shop_summary()

    def reauthorize_miaoshou_picture_space(self) -> None:
        reply = QMessageBox.question(
            self,
            "重新授权妙手图片空间",
            "软件会打开一个妙手登录窗口。\n请在窗口里完成登录/验证码，登录成功后授权会自动保存到服务器。\n确认继续吗？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.miaoshou_reauth_button.setEnabled(False)
        self.miaoshou_reauth_button.setText("授权中")
        self.shop_info_label.setText("店铺信息：已打开妙手授权窗口，请完成登录/验证码；成功后会自动保存到服务器。")
        self.reauth_signals = AutoPublishSignals()
        self.reauth_signals.finished.connect(self.on_miaoshou_reauth_finished)
        self.reauth_signals.failed.connect(self.on_miaoshou_reauth_failed)
        IMAGE_THREAD_POOL.start(MiaoshouPictureSpaceAuthTask(self.gateway, self.reauth_signals))

    def on_miaoshou_reauth_finished(self, result: dict) -> None:
        self.miaoshou_reauth_button.setEnabled(True)
        self.miaoshou_reauth_button.setText("图片空间授权")
        message = str(result.get("message") or "妙手图片空间授权已保存到服务器。")
        self.shop_info_label.setText(f"店铺信息：{message}")
        QMessageBox.information(self, "授权完成", message)
        self.refresh_miaoshou_shop_options(silent=True)

    def on_miaoshou_reauth_failed(self, error: str) -> None:
        self.miaoshou_reauth_button.setEnabled(True)
        self.miaoshou_reauth_button.setText("图片空间授权")
        self.shop_info_label.setText(f"店铺信息：妙手图片空间授权失败：{error}")
        parent = self.window()
        if self.gateway.is_invalid_token_error(error) and hasattr(parent, "clear_invalid_session"):
            parent.clear_invalid_session()
            return
        show_error_details(self, "重新授权失败", error)

    def schedule_offer_meta_sync(self) -> None:
        self.offer_meta_sync_timer.start()

    def clear_offer_meta_rows(self) -> None:
        while self.offer_meta_layout.count():
            item = self.offer_meta_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.offer_meta_rows = []

    def sync_offer_meta_rows(self) -> None:
        offer_urls = self.extract_offer_urls(self.offer_url_input.toPlainText())
        previous_values = {row.offer_url: row.collect_payload() for row in self.offer_meta_rows}
        self.clear_offer_meta_rows()
        if not offer_urls:
            empty_hint = QLabel("暂未识别到 1688 链接。")
            empty_hint.setObjectName("AutoPublishHint")
            self.offer_meta_layout.addWidget(empty_hint)
            self.offer_meta_layout.addStretch(1)
            self.update_summary_state()
            return
        for index, offer_url in enumerate(offer_urls, start=1):
            row = AutoPublishOfferRow(offer_url, index, self.offer_meta_content)
            row.restore_from(previous_values.get(offer_url, {}))
            self.offer_meta_layout.addWidget(row)
            self.offer_meta_rows.append(row)
        self.offer_meta_layout.addStretch(1)
        self.update_summary_state()

    def collect_offer_payloads(self) -> list[dict[str, Any]]:
        self.sync_offer_meta_rows()
        if not self.current_shop_id():
            QMessageBox.information(self, "请选择店铺", "请先拉取妙手店铺并选择目标店铺。")
            return []
        if len(self.offer_meta_rows) > AUTO_PUBLISH_LINK_LIMIT:
            QMessageBox.warning(
                self,
                "链接超限",
                f"单次最多支持 {AUTO_PUBLISH_LINK_LIMIT} 条 1688 链接，请拆分后再提交。",
            )
            return []
        offer_payloads: list[dict[str, Any]] = []
        for row in self.offer_meta_rows:
            offer_payloads.append(
                {
                    **row.collect_payload(),
                    "publish_count": 1,
                    "target_channel": "TikTok Shop Japan",
                    "target_language": self.language_select.currentData() or "ja",
                    "dry_run": self.dry_run.isChecked(),
                    "enable_image_translation": self.image_translation_enabled(),
                    "enable_image_removal": self.image_removal_enabled(),
                    "enable_title_optimization": self.listing_title_enabled(),
                    "enable_sku_optimization": self.listing_sku_enabled(),
                    "enable_description_optimization": self.listing_description_enabled(),
                    "remove_logo": self.smart_removal_remove_logo_enabled(),
                    "remove_transparent_text": self.smart_removal_remove_transparent_text_enabled(),
                    "remove_text": self.smart_removal_remove_text_enabled(),
                    "remove_psoriasis": self.smart_removal_remove_psoriasis_enabled(),
                    "profit_rule": self.profit_rule_input.text().strip(),
                    "pricing_currency": "JPY",
                    "target_site": "JP",
                    "target_shop_id": self.current_shop_id(),
                }
            )
        return offer_payloads

    def create_1688_task(self) -> None:
        payloads = self.collect_offer_payloads()
        if not payloads:
            QMessageBox.information(self, "请输入链接", "请先粘贴 1688 商品链接。")
            return
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
            matches = re.findall(r"https?://detail\.1688\.com/offer/\d+\.html?(?:\?[^\s|$，,；;]*)?", line, flags=re.IGNORECASE)
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
        self.progress_phase.setText("创建中")
        self.progress_label.setText("正在创建任务")
        self.reset_api_usage_panel("任务已开始，正在等待进度回传。")
        self.result.setPlainText("任务已提交，正在后台处理。完成后会自动弹出提示。")
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
        self.progress_phase.setText("创建中")
        self.progress_label.setText(f"批量任务已开始：{len(payloads)} 个链接")
        self.reset_api_usage_panel(f"批量任务已开始：{len(payloads)} 个链接，正在等待进度回传。")
        self.result.setPlainText(
            f"批量任务已提交，共 {len(payloads)} 条链接。完成后会自动弹出提示。"
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

    def animate_progress_bar(self) -> None:
        if not hasattr(self, "progress_bar"):
            return
        current_value = int(self.progress_bar.value())
        target_value = max(0, min(int(self.progress_target_value or 0), 100))
        if current_value >= target_value:
            if target_value >= 100:
                self.progress_animation_timer.stop()
            return
        diff = target_value - current_value
        if diff >= 30:
            step = 6
        elif diff >= 12:
            step = 3
        elif diff >= 4:
            step = 2
        else:
            step = 1
        next_value = min(current_value + step, target_value)
        self.progress_bar.setValue(next_value)
        if next_value >= target_value and target_value >= 100:
            self.progress_animation_timer.stop()

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
        self.progress_target_value = max(0, min(percent, 100))
        if self.progress_bar.value() > self.progress_target_value:
            self.progress_bar.setValue(self.progress_target_value)
        if self.progress_target_value > self.progress_bar.value() or self.progress_target_value >= 100:
            self.progress_animation_timer.start()
        else:
            self.progress_animation_timer.stop()
        message = str(progress.get("message") or result.get("message") or "任务处理中")
        stage = str(progress.get("stage") or result.get("status") or "processing").strip().lower()
        stage_map = {
            "pending": "等待",
            "collecting": "采集",
            "scanning": "采集",
            "translating": "翻译",
            "image": "图片",
            "images": "图片",
            "publishing": "发布",
            "imported": "完成",
            "done": "完成",
            "failed": "失败",
        }
        self.progress_phase.setText("完成" if percent >= 100 else stage_map.get(stage, "处理中"))
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
        self.progress_target_value = 100
        if not self.progress_animation_timer.isActive():
            self.progress_animation_timer.start()
        self.render_result(result)
        self.create_button.setEnabled(True)
        self.create_button.setText("开始上架")
        self.progress_phase.setText("完成")
        QMessageBox.information(self, "处理完成", result.get("message", "任务已执行。"))

    def on_task_failed(self, message: str) -> None:
        self.progress_timer.stop()
        self.progress_label.setText("任务失败")
        self.progress_phase.setText("失败")
        self.create_button.setEnabled(True)
        self.create_button.setText("开始上架")
        if self.gateway.is_invalid_token_error(ApiError(message)):
            parent = self.window()
            if hasattr(parent, "clear_invalid_session"):
                parent.clear_invalid_session()
            QMessageBox.warning(self, "登录已失效", "登录已失效，请重新登录后再执行。")
            return
        QMessageBox.warning(self, "执行失败", message)

    def reset_flow(self) -> None:
        self.progress_timer.stop()
        self.progress_animation_timer.stop()
        self.progress_target_value = 0
        self.progress_bar.setValue(0)
        self.progress_label.setText("待开始，输入 1688 链接后点击开始执行。")
        self.progress_phase.setText("待开始")
        self.reset_api_usage_panel()
        self.update_miaoshou_shop_summary()

    @staticmethod
    def format_shop_summary(result: dict[str, Any]) -> str:
        def format_item(item: dict[str, Any]) -> str:
            shop_id = item.get("shop_id")
            shop_name = str(item.get("shop_name") or "").strip()
            if shop_name and shop_id is not None:
                return f"{shop_name}（{shop_id}）"
            if shop_name:
                return shop_name
            if shop_id is not None:
                return f"店铺ID {shop_id}"
            return "未命名店铺"

        available = [item for item in (result.get("available_shops") or []) if isinstance(item, dict)]
        selected = [item for item in (result.get("selected_shops") or []) if isinstance(item, dict)]
        selected_shop_ids = [str(item.get("shop_id") or "") for item in selected if item.get("shop_id") is not None]
        if available:
            available_text = "、".join(format_item(item) for item in available[:6])
            if len(available) > 6:
                available_text += f" 等 {len(available)} 个"
            selected_text = "、".join(format_item(item) for item in selected[:6]) if selected else "未明确"
            return f"店铺信息：账号内共 {len(available)} 个店铺，{available_text}；本次选中：{selected_text}。"
        if selected:
            selected_text = "、".join(format_item(item) for item in selected[:6])
            return f"店铺信息：本次选中 {selected_text}。"
        shop_ids = [str(item) for item in (result.get("shop_ids") or []) if str(item).strip()]
        if shop_ids:
            return f"店铺信息：已选店铺ID {', '.join(shop_ids)}。"
        return "店铺信息：未获取到店铺列表。"

    def render_result(self, result: dict[str, Any]) -> None:
        if isinstance(result.get("batch_results"), list):
            self.render_batch_result(result)
            return
        self.update_api_usage_panel(result)
        self.shop_info_label.setText(self.format_shop_summary(result))
        progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
        progress_text = str(progress.get("message") or result.get("message") or "-")
        lines = [
            f"状态：{result.get('status', '-')}",
            f"消息：{result.get('message', '-')}",
            f"店铺：{self.format_shop_summary(result).replace('店铺信息：', '')}",
            f"进度：{progress_text}",
            "",
            f"结果：{('成功' if result.get('ok') else '失败')}",
        ]
        errors = result.get("errors") or []
        if errors:
            lines.append("")
            lines.append("错误：")
            lines.extend([f"- {error}" for error in errors[:3]])
        product_infos = result.get("product_infos") or []
        if len(product_infos) > 1:
            lines.append("")
            lines.append(f"商品数：{len(product_infos)}")
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
        self.shop_info_label.setText(self.format_shop_summary(result))
        progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
        progress_text = str(progress.get("message") or result.get("message") or "-")
        lines = [
            f"状态：{result.get('status', '-')}",
            f"消息：{result.get('message', '-')}",
            f"店铺：{self.format_shop_summary(result).replace('店铺信息：', '')}",
            f"进度：{progress_text}",
            "",
            f"汇总：成功 {ok_count} 个，失败 {failed_count} 个。",
            "",
            "说明：批量任务只显示总览，不展开每一步。",
        ]
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
        title_row.addWidget(QLabel("·"))
        subtitle = QLabel("点击原商品卡片查看 AI 衍生品，并对衍生品方向做拒绝原因批改。")
        subtitle.setObjectName("Muted")
        title_row.addWidget(subtitle)
        title_row.addStretch()
        title_row.addWidget(refresh_button)
        header_layout.addLayout(title_row, 1)
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
            show_error_details(self, "加载失败", exc)
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
    def __init__(self, gateway: DataGateway, product: dict[str, Any], products: list[dict[str, Any]] | None = None, product_index: int = 0, parent=None, review_mode: bool = True) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.products = products or [product]
        self.product_index = max(0, min(product_index, len(self.products) - 1))
        self.product = product
        self.review_mode = review_mode
        self.collection_saved = False
        self.generation_task_id: int | None = None
        self.generation_timer = QTimer(self)
        self.generation_timer.setInterval(1800)
        self.generation_timer.timeout.connect(self.poll_generation)
        self.setWindowTitle(f"衍生品审核 - {str(self.product.get('title') or '')[:40]}")
        self.setMinimumSize(1000, 650)
        self.resize(1220, 800)
        layout = QVBoxLayout(self)
        self.header = QFrame()
        self.header.setObjectName("PageHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(14)
        self.header_image_box = QWidget()
        self.header_image_layout = QVBoxLayout(self.header_image_box)
        self.header_image_layout.setContentsMargins(0, 0, 0, 0)
        self.header_image_layout.setSpacing(0)
        self.header_image_layout.addWidget(create_product_image("", "📦", 86, 86))
        header_layout.addWidget(self.header_image_box, 0, Qt.AlignTop)
        header_text = QVBoxLayout()
        header_text.setSpacing(6)
        self.header_title = QLabel()
        self.header_title.setObjectName("DerivedDialogTitle")
        self.header_title.setWordWrap(True)
        self.header_title.setMinimumWidth(0)
        self.header_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_text.addWidget(self.header_title)
        header_subtitle = QLabel("审核对象是 AI 衍生品，不是具体 1688 商品。")
        header_subtitle.setObjectName("Muted")
        header_subtitle.setWordWrap(True)
        header_text.addWidget(header_subtitle)
        header_layout.addLayout(header_text, 1)
        layout.addWidget(self.header)
        self._update_header()

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
        self.generation_progress = QProgressBar()
        self.generation_progress.setRange(0, 100)
        self.generation_progress.setFixedWidth(210)
        self.generation_progress.setFormat("衍生处理中 %p%")
        self.generation_progress.hide()
        self.generate_button = QPushButton("开始衍生")
        self.generate_button.setObjectName("PrimaryAction")
        self.generate_button.clicked.connect(self.start_generation)
        if not self.review_mode:
            self.collection_items: list[dict[str, Any]] = []
            self.load_collection_items()
        next_button = None
        if self.review_mode:
            next_button = QPushButton("下一个原商品")
            next_button.setObjectName("PrimaryAction")
            next_button.clicked.connect(self.next_product)
        footer_layout.addWidget(self.product_progress)
        footer_layout.addStretch()
        footer_layout.addWidget(self.generation_progress)
        credit_action = QHBoxLayout()
        credit_action.setContentsMargins(0, 0, 0, 0)
        credit_action.setSpacing(7)
        credit_action.addWidget(self.generate_button)
        self.credit_label = QLabel("10积分")
        self.credit_label.setObjectName("CreditHint")
        credit_action.addWidget(self.credit_label)
        footer_layout.addLayout(credit_action)
        if next_button is not None:
            footer_layout.addWidget(next_button)
        layout.addWidget(footer)

        self.refresh_cards()

    def set_product(self, product: dict[str, Any]) -> None:
        self.product = product
        self.setWindowTitle(f"衍生品审核 - {str(self.product.get('title') or '')[:40]}")
        self._update_header()
        self.refresh_cards()

    def refresh_credit_state(self) -> None:
        if not getattr(self, "generation_task_id", None):
            balance = int((self.gateway.user or {}).get("credit_balance") or 0)
            self.generate_button.setEnabled(balance >= 10)

    def _update_header(self) -> None:
        while self.header_image_layout.count():
            child = self.header_image_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        image_url = str(self.product.get("image_url") or self.product.get("supplier_image_url") or "")
        self.header_image_layout.addWidget(create_product_image(image_url, "📦", 86, 86))
        self.header_title.setText(str(self.product.get("title") or "未命名原商品"))
        
    def load_collection_items(self) -> None:
        try:
            self.collection_items = self.gateway.favorites()
        except Exception:
            self.collection_items = []

    @staticmethod
    def collection_key(item: dict[str, Any]) -> tuple[str, str]:
        return (
            str(item.get("title") or item.get("derived_title") or ""),
            str(item.get("image_url") or item.get("supplier_image_url") or ""),
        )

    def toggle_item_collection(self, item: dict[str, Any], button: QPushButton) -> None:
        try:
            key = self.collection_key(item)
            saved = next((favorite for favorite in self.collection_items if self.collection_key(favorite) == key), None)
            if saved:
                self.gateway.delete_favorite(int(saved["id"]))
                self.collection_items = [favorite for favorite in self.collection_items if int(favorite.get("id") or 0) != int(saved["id"])]
                button.setText("加入采集箱")
            else:
                snapshot = dict(item)
                snapshot["source_type"] = "derived"
                created = self.gateway.create_favorite(snapshot)
                self.collection_items.insert(0, created)
                button.setText("已在采集箱")
        except Exception as exc:
            show_error_details(self, "采集失败", exc)

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
                show_error_details(self, "加载失败", exc)
                items = []
        if not items:
            empty = QLabel("暂无衍生品，点击下方“开始衍生”进行翻译、分族、AI生成和1688匹配。")
            empty.setObjectName("Muted")
            self.cards.addWidget(empty)
        for item in items:
            self.cards.addWidget(self.card(item))
        self.cards.addStretch()
        self.product_progress.setText(f"原商品 {self.product_index + 1}/{len(self.products)}")
        self.generate_button.setText("重新衍生" if items else "开始衍生")
        balance = int((self.gateway.user or {}).get("credit_balance") or 0)
        self.generate_button.setEnabled(not bool(self.generation_task_id) and balance >= 10)

    def start_generation(self) -> None:
        try:
            result = self.gateway.start_product_full_pipeline(int(self.product["id"]))
            if "credit_balance" in result and self.gateway.user is not None:
                self.gateway.user["credit_balance"] = result.get("credit_balance")
                parent = self.window()
                if hasattr(parent, "user"):
                    parent.user = self.gateway.user
                if hasattr(parent, "update_login_status"):
                    parent.update_login_status()
            self.generation_task_id = int(result["task_id"])
            self.generation_progress.setValue(0)
            self.generation_progress.show()
            self.generate_button.setEnabled(False)
            self.generation_timer.start()
            self.product_progress.setText("正在执行：翻译、分族、衍生、1688匹配")
        except Exception as exc:
            if "积分不足" in str(exc):
                show_credit_recharge_prompt(self)
            else:
                QMessageBox.warning(self, "启动失败", str(exc))

    def poll_generation(self) -> None:
        if not self.generation_task_id:
            return
        try:
            result = self.gateway.product_full_pipeline_task(self.generation_task_id)
            self.generation_progress.setValue(int(result.get("progress") or 0))
            self.product_progress.setText(str(result.get("message") or "正在处理"))
            if result.get("status") in {"success", "failed"}:
                self.generation_timer.stop()
                task_failed = result.get("status") == "failed"
                self.generation_task_id = None
                self.generation_progress.hide()
                self.refresh_credit_state()
                if task_failed:
                    QMessageBox.warning(self, "衍生失败", str(result.get("error_message") or result.get("message") or "任务失败"))
                else:
                    self.refresh_cards()
        except Exception as exc:
            self.generation_timer.stop()
            self.generation_task_id = None
            self.generation_progress.hide()
            self.refresh_credit_state()
            QMessageBox.warning(self, "任务查询失败", str(exc))

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
        if self.review_mode:
            reject = QPushButton("拒绝")
            reject.clicked.connect(lambda: self.reject_item(item))
            head.addWidget(reject)
        else:
            collected = any(self.collection_key(saved) == self.collection_key(item) for saved in self.collection_items)
            collect = QPushButton("已在采集箱" if collected else "加入采集箱")
            collect.setObjectName("SecondaryAction")
            collect.clicked.connect(lambda checked=False, selected=item, button=collect: self.toggle_item_collection(selected, button))
            head.addWidget(collect)
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


class MultiSelectComboBox(QComboBox):
    """可勾选下拉框，用于一次选择多个拒绝维度。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("请选择拒绝维度")
        self.view().pressed.connect(self._toggle_item)

    def add_check_item(self, text: str, data: Any) -> None:
        self.addItem(text, data)
        item = self.model().item(self.count() - 1)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)

    def _toggle_item(self, index) -> None:
        item = self.model().itemFromIndex(index)
        if item is None:
            return
        state = item.data(Qt.CheckStateRole)
        item.setData(Qt.Unchecked if state == Qt.Checked else Qt.Checked, Qt.CheckStateRole)
        self._update_text()
        QTimer.singleShot(0, self.showPopup)

    def _update_text(self) -> None:
        labels = []
        for index in range(self.count()):
            item = self.model().item(index)
            if item.data(Qt.CheckStateRole) == Qt.Checked:
                labels.append(str(item.text()))
        self.lineEdit().setText("、".join(labels) if labels else "请选择拒绝维度")

    def selected_data(self) -> list[Any]:
        return [
            self.itemData(index)
            for index in range(self.count())
            if self.model().item(index).data(Qt.CheckStateRole) == Qt.Checked
        ]


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
        self.reason = MultiSelectComboBox()
        self.reason.setObjectName("ReasonCombo")
        self.reason.setMinimumHeight(42)
        self.attributes = gateway.attributes()
        for attr in self.attributes:
            self.reason.add_check_item(attr["attribute_name"], attr["id"])
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
        attribute_ids = [int(value) for value in self.reason.selected_data() if value is not None]
        if not attribute_ids:
            QMessageBox.information(self, "请选择属性", "请至少选择一个拒绝维度。")
            return
        self.gateway.reject(self.item["id"], attribute_ids, self.comment.toPlainText())
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
        "bg": "#f7f9fb",
        "sidebar": "#ffffff",
        "panel": "#ffffff",
        "panel2": "#fbfcfd",
        "hero": "#effaf6",
        "input": "#fbfcfd",
        "border": "#e4ebef",
        "text": "#24324a",
        "muted": "#7b8798",
        "accent": "#159878",
        "accent_hover": "#117f66",
        "tag": "#e8f7f1",
        "tag_text": "#17846e",
        "image_a": "#edf7f4",
        "image_b": "#fff2ef",
        "metric": "#f4f7f9",
    },
}


def apply_style(app: QApplication, theme_name: str = "light") -> None:
    theme = THEMES.get(theme_name, THEMES["light"])
    theme = dict(theme)
    theme["app_dir"] = "file:///" + str(APP_DIR).replace("\\", "/").lstrip("/")
    app.setFont(QFont("Microsoft YaHei UI", 13))
    qss = Template(
        """
        QWidget { background: $bg; color: $text; }
        QLineEdit, QTextEdit, QComboBox {
            background: $input; color: $text; border: 1px solid $border; border-radius: 9px;
            padding: 9px 11px; selection-background-color: $accent;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid $accent;
        }
        QComboBox {
            min-height: 38px; padding: 0 36px 0 13px; font-size: 13px;
        }
        QComboBox:hover { border-color: $accent; background: $panel; }
        QComboBox::drop-down {
            width: 32px; border: 0; border-left: 1px solid $border;
            background: transparent;
        }
        QComboBox::down-arrow {
            image: url($app_dir/assets/icons/combo_chevron.svg);
            width: 12px; height: 8px;
        }
        QComboBox QAbstractItemView {
            background: $panel; color: $text; border: 1px solid $border;
            border-radius: 10px; padding: 5px; outline: 0;
            selection-background-color: $tag; selection-color: $accent;
        }
        QComboBox QAbstractItemView::item {
            min-height: 32px; padding: 7px 10px; border-radius: 7px;
        }
        QComboBox QAbstractItemView::item:hover {
            background: $tag; color: $accent;
        }
        #ReasonCombo {
            background: $panel; color: $text; border: 1px solid $accent;
            border-radius: 10px; padding: 9px 12px; font-size: 15px; font-weight: 800;
        }
        #ReasonCombo::drop-down {
            width: 34px; border: 0; border-left: 1px solid $border;
        }
        #ReasonCombo QAbstractItemView {
            background: $panel; border: 1px solid $accent; border-radius: 10px;
            padding: 6px; selection-background-color: $tag; selection-color: $accent;
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
            background: rgba(21, 152, 120, 38); color: #17846e;
            border: 1px solid rgba(21, 152, 120, 70); border-radius: 8px;
            padding: 9px 16px; min-height: 34px; font-weight: 700; outline: 0;
        }
        QPushButton:focus { outline: 0; }
        QPushButton:hover { background: rgba(21, 152, 120, 58); }
        QPushButton:pressed { background: rgba(21, 152, 120, 78); }
        QPushButton:disabled { background: rgba(148, 163, 184, 32); color: $muted; border-color: $border; }
        QTableWidget {
            background: $panel; alternate-background-color: $panel2; color: $text;
            border: 1px solid $border; border-radius: 8px; gridline-color: $border;
        }
        QTableWidget::item { padding: 8px; border: 0; }
        QTableWidget::item:selected { background: $accent; color: #ffffff; }
        #CollectionTable { border: 1px solid $border; border-radius: 10px; }
        #CollectionTable QHeaderView::section {
            background: $panel2; color: $text; padding: 11px 10px; border: 0;
            font-size: 13px; font-weight: 800;
        }
        #CollectionTitle { background: transparent; color: $text; font-size: 13px; font-weight: 700; }
        #CollectionText { background: transparent; color: $muted; font-size: 13px; }
        #CollectionPrice { background: transparent; color: #ef6461; font-size: 15px; font-weight: 900; }
        #CollectionLink { background: transparent; color: $accent; border: 0; padding: 0; min-height: 0; font-size: 12px; }
        #CollectionLink:hover { background: transparent; color: #0f6f5b; }
        #CollectionReference { background: transparent; color: $muted; font-size: 12px; }
        #CollectionAction { min-height: 28px; padding: 5px 10px; font-size: 12px; }
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
        #LoginModeTab {
            background: transparent; color: $muted; border: 0; border-bottom: 2px solid transparent;
            border-radius: 0; padding: 8px 5px; font-size: 13px; font-weight: 800;
        }
        #LoginModeTab:hover { color: $accent; border-bottom-color: $accent; }
        #LoginQrTitle { background: transparent; color: $text; font-size: 17px; font-weight: 800; }
        #LoginQrPlaceholder {
            background: $panel2; color: $muted; border: 1px solid $border;
            border-radius: 8px; font-size: 14px; font-weight: 700;
        }
        #Muted { color: $muted; background: transparent; }
        #SidePanel { background: $sidebar; border-right: 1px solid $border; }
        #BrandBox {
            background: $sidebar; border-bottom: 1px solid $border;
        }
        #BrandTitle {
            background: transparent; color: $text; font-size: 16px; font-weight: 900;
        }
        #BrandSub {
            background: transparent; color: $muted; font-size: 11px; letter-spacing: 0px;
        }
        #SideNav {
            background: $sidebar; color: $muted; border: 0; padding: 16px 10px;
            outline: 0; font-family: "Microsoft YaHei UI"; font-size: 14px; font-weight: 500;
        }
        #SideNav::item {
            height: 50px; border-radius: 8px; margin: 5px 0; padding-left: 10px;
            font-family: "Microsoft YaHei UI"; font-size: 14px; font-weight: 700; text-align: center;
        }
        #SideNav::item:hover { background: $panel2; color: $text; }
        #SideNav::item:selected { background: rgba(21, 152, 120, 38); color: #17846e; }
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
        #SideLoginButton:hover { background: rgba(21, 152, 120, 58); color: #17846e; }
        #IconButton {
            background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70);
            border-radius: 8px; font-size: 13px; font-weight: 800;
        }
        #IconButton:hover { background: rgba(21, 152, 120, 58); color: #17846e; }
        #Page { background: $bg; }
        #StudioHeader { background: transparent; }
        #StudioTitle { background: transparent; color: $text; font-size: 26px; font-weight: 900; }
        #StudioChat, #StudioReport {
            background: $panel; border: 1px solid $border; border-radius: 12px;
        }
        #StudioChat { background: $hero; border-color: #d9eee7; }
        #LibraryAttributes {
            background: $panel; border: 1px solid $border; border-radius: 12px;
        }
        #LibraryAttributeCard {
            background: $panel2; border: 1px solid $border; border-radius: 7px;
        }
        #LibraryAttributeCard:hover { border-color: $accent; background: $tag; }
        #LibraryAttributeName { background: transparent; color: $text; font-size: 13px; font-weight: 800; }
        #LibraryAttributeValue { background: transparent; color: $accent; font-size: 11px; font-weight: 900; }
        #StudioReportIcon { background: $tag; color: $accent; border-radius: 14px; font-size: 14px; font-weight: 900; }
        #StudioReportPrice { background: transparent; color: #ef6461; font-size: 18px; font-weight: 900; }
        #StudioDimensionTable { background: $panel; border: 1px solid $border; border-radius: 9px; }
        #StudioDimensionRow { background: transparent; border-bottom: 1px solid $border; }
        #StudioDimensionRow:last-child { border-bottom: 0; }
        #StudioDimensionIcon { background: $tag; color: $accent; border-radius: 14px; font-size: 14px; font-weight: 900; }
        #StudioTutorial {
            background: $panel; color: $muted; border: 1px solid $border;
            border-radius: 8px; padding: 8px 12px; font-size: 11px; font-weight: 700;
        }
        #StudioTutorial:hover { color: $accent; border-color: $accent; }
        #StudioMarket { background: transparent; color: $muted; font-size: 11px; }
        #StudioPromptIcon { background: transparent; color: #4e75f6; font-size: 17px; font-weight: 900; }
        #StudioPromptCount { background: transparent; color: $muted; font-size: 10px; }
        #CreditHint { background: transparent; color: $muted; font-size: 10px; font-weight: 500; }
        #StudioChat QLineEdit {
            background: $panel; border: 1px solid $border; border-radius: 8px;
            padding: 10px 12px; color: $text; font-size: 12px;
        }
        #StudioChat QLineEdit:focus { border: 1px solid #4e75f6; }
        #StudioPromptFrame { background: $panel; border: 1px solid $border; border-radius: 10px; }
        #StudioPromptFrame:focus-within { border: 1px solid #16a085; }
        #StudioPromptEditor { background: transparent; color: $text; border: 0; padding: 10px 12px 48px 12px; font-size: 13px; }
        #StudioBubbleUser, #StudioBubbleAi {
            border-radius: 8px; border: 1px solid $border;
        }
        #StudioBubbleUser { background: $tag; }
        #StudioBubbleAi { background: $panel; }
        #StudioBubbleText { background: transparent; color: $text; font-size: 12px; }
        #StudioPanelTitle { background: transparent; color: $text; font-size: 16px; font-weight: 900; }
        #StudioDot { background: transparent; color: #16a085; font-size: 16px; }
        #StudioPromptTitle { background: transparent; color: $text; font-size: 16px; font-weight: 800; }
        #StudioPromptHint { background: transparent; color: $muted; font-size: 13px; }
        #StudioModeCombo { min-width: 108px; min-height: 38px; padding: 0 24px 0 12px; color: $text; background: $panel; border: 1px solid $border; border-radius: 8px; }
        #StudioAnalyze { background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70); border-radius: 8px; min-width: 122px; min-height: 38px; font-weight: 800; }
        #StudioAnalyze:hover { background: rgba(21, 152, 120, 58); }
        #StudioPrimary {
            background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70); border-radius: 8px;
            min-width: 112px; min-height: 38px; font-weight: 800;
        }
        #StudioPrimary:hover { background: rgba(21, 152, 120, 58); }
        #StudioSecondaryAction {
            background: rgba(21, 152, 120, 24); color: #17846e; border: 1px solid rgba(21, 152, 120, 70);
            border-radius: 8px; min-height: 38px; font-weight: 800;
        }
        #StudioSecondaryAction:hover { color: $accent; border-color: $accent; }
        #StudioSecondaryAction:disabled, #StudioPrimary:disabled { color: $muted; background: $metric; }
        #RankFilterLabel { background: transparent; color: $text; font-size: 14px; font-weight: 700; padding-left: 2px; }
        #RankFilterPanel { background: transparent; border-bottom: 1px solid $border; }
        #RankFilterDate {
            min-width: 142px; min-height: 38px; padding: 0 38px 0 14px;
            background: $panel; color: $text; border: 1px solid $border;
            border-radius: 11px; font-size: 13px; font-weight: 700;
        }
        #RankFilterDate:hover { border-color: $accent; background: $panel2; }
        #RankFilterDate:focus { border: 1px solid $accent; }
        #RankFilterDate::drop-down {
            width: 34px; border: 0; border-left: 1px solid $border;
            background: transparent;
        }
        #RankFilterDate::down-arrow {
            image: url($app_dir/assets/icons/calendar.svg);
            width: 16px; height: 16px;
        }
        QCalendarWidget {
            background: $panel; color: $text; border: 1px solid $border;
            border-radius: 12px;
        }
        QCalendarWidget QWidget#qt_calendar_navigationbar {
            background: $hero; border: 0; border-top-left-radius: 11px;
            border-top-right-radius: 11px; min-height: 38px;
        }
        QCalendarWidget QToolButton {
            background: transparent; color: $text; border: 0; border-radius: 7px;
            padding: 5px 8px; font-size: 13px; font-weight: 800;
        }
        QCalendarWidget QToolButton:hover { background: $tag; color: $accent; }
        QCalendarWidget QMenu { background: $panel; color: $text; border: 1px solid $border; }
        QCalendarWidget QSpinBox {
            background: $panel; color: $text; border: 1px solid $border;
            border-radius: 6px; padding: 3px 5px;
        }
        QCalendarWidget QAbstractItemView {
            background: $panel; color: $text; selection-background-color: $accent;
            selection-color: #ffffff; outline: 0; border: 0;
        }
        #RankFilterOption { background: transparent; color: $muted; border: 0; border-radius: 16px; padding: 7px 12px; min-height: 30px; font-size: 13px; }
        #RankFilterOption:hover { color: $accent; background: $tag; }
        #RankFilterOption:checked { color: #17846e; background: rgba(21, 152, 120, 38); border: 1px solid rgba(21, 152, 120, 70); font-weight: 800; }
        #RankFilterViewButton { background: $tag; color: $accent; border: 1px solid $border; border-radius: 8px; min-height: 32px; font-weight: 800; }
        #RankFilterViewButton:hover { background: rgba(21, 152, 120, 58); color: #17846e; }
        #StudioChip {
            background: rgba(21, 152, 120, 24); color: #17846e; border: 1px solid rgba(21, 152, 120, 70);
            border-radius: 14px; padding: 5px 12px; font-size: 11px;
        }
        #StudioChip:hover { color: $accent; border-color: $accent; }
        #StudioIconButton {
            background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70); border-radius: 10px;
        }
        #StudioIconButton:hover { background: rgba(21, 152, 120, 58); }
        #StudioSectionTitle { background: transparent; color: $text; font-size: 17px; font-weight: 900; }
        #StudioScroll { background: transparent; border: 0; }
        #StudioCarousel { background: transparent; }
        #StudioGrid { background: transparent; }
        #StudioReport { background: $panel2; }
        #StudioReportTitle { background: transparent; color: $text; font-size: 18px; font-weight: 900; line-height: 1.3; }
        #StudioDimension {
            background: $panel; border: 1px solid $border; border-radius: 8px;
        }
        #StudioDimensionName { background: transparent; color: $text; font-size: 14px; font-weight: 800; }
        #StudioDimensionGrade { background: transparent; color: $accent; font-size: 14px; font-weight: 800; }
        #StudioDimensionText { background: transparent; color: $muted; font-size: 14px; line-height: 1.25; }
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
            background: $panel; border: 1px solid $border; border-radius: 9px;
        }
        #StudioNewCard:hover { border: 1px solid $accent; }
        #StudioNewName { background: transparent; color: $text; font-size: 12px; font-weight: 800; }
        #StudioNewTag {
            background: $tag; color: $tag_text; border-radius: 5px; padding: 3px 7px;
            font-size: 10px; font-weight: 700;
        }
        #StudioNewPrice { background: transparent; color: #ef6461; font-size: 17px; font-weight: 900; }
        #StudioNewMuted { background: transparent; color: $muted; font-size: 10px; }
        #StudioSummaryText { background: $panel; color: $muted; border-radius: 7px; padding: 7px 9px; font-size: 14px; }
        #StudioReportTab {
            background: transparent; color: $muted; border: 0; border-bottom: 2px solid transparent;
            border-radius: 0; padding: 7px 4px; font-size: 13px; font-weight: 700;
        }
        #StudioReportTab:checked { color: $tag_text; border-bottom: 2px solid $tag_text; }
        #PageHeader {
            background: $panel; border: 1px solid $border; border-radius: 14px;
        }
        #PageTitle { background: transparent; font-size: 28px; font-weight: 900; color: $text; }
        #DerivedDialogTitle { background: transparent; font-size: 22px; font-weight: 800; color: $text; }
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
        #Panel {
            background: $panel; border: 1px solid $border; border-radius: 12px;
        }
        #PersonalValue { background: transparent; color: $text; font-size: 15px; font-weight: 800; }
        #CardTitle { background: transparent; color: $text; font-size: 16px; font-weight: 800; }
        #AutoPublishSection {
            background: linear-gradient(180deg, #f7fbfa 0%, #f4f8fb 100%);
            border-radius: 18px;
        }
        #AutoPublishCard {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $panel, stop:1 $panel2);
            border: 1px solid $border;
            border-radius: 16px;
        }
        #AutoPublishSidePanel {
            background: $panel; border: 1px solid $border; border-radius: 14px;
        }
        #AutoPublishOfferCard {
            background: $panel2; border: 1px solid $border; border-radius: 12px;
        }
        #AutoPublishIndex {
            background: $tag; color: $accent; border: 1px solid $border; border-radius: 18px;
            font-size: 12px; font-weight: 900;
        }
        #AutoPublishUrl {
            background: transparent; color: $text; font-size: 13px; font-weight: 700;
        }
        #AutoPublishHint {
            background: transparent; color: $muted; font-size: 12px; line-height: 1.35;
        }
        #AutoPublishShopInfo {
            background: #f3faf8;
            color: $text;
            border: 1px solid rgba(22, 160, 133, 0.18);
            border-radius: 12px;
            padding: 8px 12px;
            font-size: 12px;
            line-height: 1.35;
        }
        #AutoPublishShopCombo {
            background: $input;
            color: $text;
            border: 1px solid $border;
            border-radius: 12px;
            padding: 6px 12px;
            font-size: 13px;
            min-height: 34px;
        }
        #AutoPublishShopCombo:hover {
            border-color: $accent;
        }
        #AutoPublishShopCombo:disabled {
            background: $panel2;
            color: $muted;
        }
        #AutoPublishShopRefresh {
            background: $tag;
            color: $tag_text;
            border: 1px solid rgba(22, 160, 133, 0.18);
            border-radius: 10px;
            min-height: 30px;
            min-width: 76px;
            font-weight: 800;
            font-size: 12px;
        }
        #AutoPublishShopRefresh:hover {
            background: $accent;
            color: #ffffff;
        }
        #AutoPublishShopRefresh:disabled {
            color: $muted;
            background: $metric;
        }
        #AutoPublishReauth {
            background: $tag;
            color: $tag_text;
            border: 1px solid rgba(22, 160, 133, 0.18);
            border-radius: 10px;
            min-height: 30px;
            min-width: 104px;
            font-size: 12px;
            font-weight: 800;
        }
        #AutoPublishReauth:hover {
            background: $accent;
            color: #ffffff;
        }
        #AutoPublishReauth:disabled {
            color: $muted;
            background: $metric;
        }
        #AutoPublishPrimaryAction {
            background: $accent;
            color: #ffffff;
            border: 1px solid $accent;
            border-radius: 10px;
            min-height: 30px;
            min-width: 96px;
            font-size: 12px;
            font-weight: 900;
        }
        #AutoPublishPrimaryAction:hover { background: $accent_hover; }
        #AutoPublishPrimaryAction:disabled {
            color: $muted;
            background: $metric;
            border-color: $border;
        }
        #AutoPublishSecondaryAction {
            background: $panel;
            color: $accent;
            border: 1px solid $accent;
            border-radius: 10px;
            min-height: 30px;
            min-width: 66px;
            font-size: 12px;
            font-weight: 800;
        }
        #AutoPublishSecondaryAction:hover { background: $tag; }
        #AutoPublishPill {
            background: $tag; color: $accent; border: 1px solid $border;
            border-radius: 999px; padding: 5px 11px; font-size: 11px; font-weight: 800;
        }
        #AutoPublishInput {
            background: $input; color: $text; border: 1px solid $border; border-radius: 12px;
            padding: 12px 14px; font-size: 14px;
        }
        #AutoPublishSpecBox {
            background: $input; border: 1px solid $border; border-radius: 10px;
        }
        #AutoPublishSpecBox QSpinBox {
            background: $input; color: $text; border: 1px solid $border; border-radius: 9px;
            padding: 2px 6px; min-height: 24px; selection-background-color: $accent;
        }
        #AutoPublishSpecBox QSpinBox:focus {
            border: 1px solid $accent;
        }
        #AutoPublishSpecBox QSpinBox::up-button,
        #AutoPublishSpecBox QSpinBox::down-button {
            width: 0; border: 0; background: transparent;
        }
        #AutoPublishSpecBox QSpinBox::up-arrow,
        #AutoPublishSpecBox QSpinBox::down-arrow {
            width: 0; height: 0;
        }
        QProgressBar {
            background: $input; color: $text; border: 1px solid $border; border-radius: 6px;
            text-align: center; font-size: 11px;
        }
        QProgressBar::chunk {
            background: $accent; border-radius: 6px;
        }
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
            background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70); min-width: 130px;
        }
        #SecondaryAction {
            background: rgba(21, 152, 120, 24); color: #17846e; border: 1px solid rgba(21, 152, 120, 70);
            min-width: 130px;
        }
        #SecondaryAction:hover { background: $tag; }
        #ProductDeriveView {
            background: rgba(78, 117, 246, 38); color: #3d62d7; border: 1px solid rgba(78, 117, 246, 70); min-width: 0; padding: 4px 7px; font-size: 11px;
        }
        #ProductDeriveView:hover { background: rgba(78, 117, 246, 58); }
        #ProductDeriveAvailable {
            background: rgba(21, 152, 120, 38); color: #17846e; border: 1px solid rgba(21, 152, 120, 70); min-width: 0; padding: 4px 7px; font-size: 11px;
        }
        #ProductDeriveAvailable:hover { background: rgba(21, 152, 120, 58); }
        #ProductDeriveDisabled {
            background: $metric; color: $muted; border: 1px solid $border; min-width: 0; padding: 4px 7px; font-size: 11px;
        }
        #ProductCollect {
            background: rgba(21, 152, 120, 24); color: #17846e; border: 1px solid rgba(21, 152, 120, 70);
            border-radius: 7px; padding: 4px 7px; font-size: 11px; font-weight: 800;
        }
        #ProductCollect:hover { background: $tag; border-color: $accent; }
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
        #CarouselNext:hover { background: rgba(21, 152, 120, 58); color: #17846e; }
        #ProductGridWrap { background: $bg; }
        #ProductCard, #TeacherProductCard, #CompactProductCard {
            background: $panel; border: 1px solid $border; border-radius: 10px;
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
    text_selection_filter = TextSelectionFilter(app)
    app.installEventFilter(text_selection_filter)
    app.setWindowIcon(QIcon(icon_path("tk_brand.png")))
    apply_style(app)
    gateway = DataGateway()
    window = MainWindow(gateway)
    for label in window.findChildren(QLabel):
        enable_label_selection(label)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
