from __future__ import annotations

import sys
import json
import math
import base64
import mimetypes
from io import BytesIO
from pathlib import Path
from datetime import date, datetime
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QDate, QEvent, QObject, QPointF, QRunnable, QRectF, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QPolygonF
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


APP_DIR = Path(__file__).resolve().parent
ICON_DIR = APP_DIR / "assets" / "icons"
MENU_ICON_MAP = {
    "智能选品": "menu_ai.svg",
    "选品库": "menu_library.svg",
    "新品榜单": "menu_new.svg",
    "采集箱": "menu_favorite.svg",
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
}

MENU_ROLE_ACCESS = {
    "admin": None,
    "teacher": {
        "数据看板", "个人中心", "关于益行", "教师看板", "选品属性", "新品榜单", "智能选品",
    },
    "student": {
        "智能选品", "选品库", "新品榜单", "采集箱", "店铺管理", "关于益行", "个人中心",
    },
}


def icon_path(filename: str) -> str:
    return str(ICON_DIR / filename)


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
        self.analyze_button.setFixedSize(126, 38)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        margin = 10
        button_width = self.analyze_button.width()
        self.analyze_button.move(self.width() - button_width - margin, self.height() - self.analyze_button.height() - margin)
        self.count_label.adjustSize()
        self.count_label.move(self.analyze_button.x() - self.count_label.width() - 14, self.height() - self.count_label.height() - 21)



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
        return self.client.post(
            "/api/favorites",
            {
                "source_type": "new_product" if item.get("source_type") == "new_product" else "derived",
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

    def delete_attribute(self, attribute_id: int) -> dict[str, Any]:
        return self.client.delete(f"/api/admin/selection-attributes/{attribute_id}")

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


class LoginDialog(QDialog):
    def __init__(self, gateway: DataGateway, parent=None) -> None:
        super().__init__(parent)
        self.gateway = gateway
        self.user: dict[str, Any] | None = None
        self.setWindowTitle("用户登录")
        self.setWindowIcon(QIcon(icon_path("tk_brand.png")))
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
            item.setIcon(QIcon(icon_path(icon_name)))
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
        self.add_nav_separator()
        self.add_page("店铺管理", AutoPublishPage(self.gateway), "10_TK跨境助手.ico")
        self.add_page("数据看板", DataDashboardPage(self.gateway), "07_第三方API.ico")
        self.add_nav_separator()
        self.add_page("个人中心", PersonalCenterPage(self.gateway, self.apply_theme, self.apply_font), "menu_settings.svg")
        self.add_page("关于益行", InfoPage("关于益行", "益行跨境 AI 平台", "益行跨境 AI 平台专注 TikTok 日本站跨境选品、商品分析、1688 货源匹配和店铺运营。\n\n当前版本：1.0.0\n服务地址：" + self.gateway.client.base_url), "menu_settings.svg")
        self.add_nav_separator()
        self.add_page("教师看板", TeacherDashboardPage(self.gateway), "02_教师看板.ico")
        self.add_page("任务看板", PipelinePage(self.gateway), "07_第三方API.ico")
        self.add_page("用户管理", AdminUsersPage(self.gateway), "03_用户管理.ico")
        self.add_page("模型配置", SimpleConfigPage("模型配置", self.gateway.model_configs, ["配置名称", "服务商", "类型", "Base URL", "模型", "Key", "使用中"], self.gateway, "model"), "04_模型配置.ico")
        self.add_page("模型测试", ModelTestPage(self.gateway), "04_模型配置.ico")
        self.add_page("第三方 API", SimpleConfigPage("第三方 API 配置", self.gateway.third_party_configs, ["配置名称", "服务类型", "状态"], self.gateway, "third"), "07_第三方API.ico")
        self.add_page("选品属性", AttributePage(self.gateway), "08_选品属性.ico")

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
            self.setWindowTitle(f"益行跨境AI平台 - {self.user.get('real_name') or '系统管理员'}")
            self.apply_menu_permissions()
            return
        self.user_avatar.setText("未")
        self.user_name.setText("未登录")
        self.user_role.setText("请登录服务器账号")
        self.user_status.setText("登录后连接后端服务")
        self.login_button.setText("登录")
        self.setWindowTitle("益行跨境AI平台")
        self.apply_menu_permissions()

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
        password_layout.addWidget(QLabel("修改密码"))
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
        password_layout.addWidget(ThemeSettingsPanel(on_theme_change or (lambda _: None), on_font_change))
        password_layout.addStretch()
        body.addWidget(password_panel, 1)

        recharge_panel = QFrame()
        recharge_panel.setObjectName("Panel")
        recharge_layout = QVBoxLayout(recharge_panel)
        recharge_layout.setContentsMargins(18, 16, 18, 18)
        recharge_layout.setSpacing(10)
        recharge_layout.addWidget(QLabel("积分充值"))
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
        self.layout.addLayout(body, 1)
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
        panel_layout.addStretch()
        self.layout.addWidget(panel, 1)


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
        metrics = QHBoxLayout()
        price_label = QLabel(format_jpy_price(price))
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
        refresh_button = QPushButton()
        refresh_button.setObjectName("IconButton")
        refresh_button.setFixedSize(34, 34)
        refresh_button.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh_button.setIconSize(QSize(17, 17))
        refresh_button.setToolTip("刷新商品数据")
        refresh_button.clicked.connect(self.force_refresh)
        self.data_refresh_button = refresh_button
        heading.addWidget(refresh_button)
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
        for tab_name in ("选品分析报告", "人群匹配", "使用场景"):
            tab = QPushButton(tab_name)
            tab.setObjectName("StudioReportTab")
            tab.setCheckable(True)
            tab.setChecked(tab_name == "选品分析报告")
            tab.clicked.connect(lambda checked=False, name=tab_name, button=tab: self._select_report_tab(name, button))
            self.report_tab_buttons.append(tab)
            report_tabs.addWidget(tab)
        report_layout.addLayout(report_tabs)
        self.report_dimensions = QVBoxLayout()
        self.report_dimensions.setSpacing(6)
        report_layout.addLayout(self.report_dimensions)
        report_hint = QLabel("点击新品卡片查看完整维度报告")
        report_hint.setObjectName("Muted")
        report_hint.setWordWrap(True)
        report_layout.addWidget(report_hint)
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
        self.report_tab = "选品分析报告"
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
        self.report_price.setText(format_jpy_price(price))
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(f"销量 {sales:,} · AI 参考 {float(score):.0f} 分")
        image = create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140)
        self.report_image_layout.addWidget(image)
        title_key = str(item.get("title") or item.get("derived_title") or "")
        image_key = str(item.get("image_url") or item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        self.favorite_button.setText("★  已在采集箱" if saved else "☆  加入采集箱")
        dimensions = dimension_items_from_report(item)
        if self.report_tab == "人群匹配":
            dimensions = [row for row in dimensions if row[0] in {"目标群体", "日本偏好", "竞品属性"}]
        elif self.report_tab == "使用场景":
            dimensions = [row for row in dimensions if row[0] in {"使用场景", "商品周期性", "复购属性"}]
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
        self.report_tab = "选品分析报告"
        self.favorite_items: list[dict[str, Any]] = []
        self.layout.setContentsMargins(28, 22, 28, 22)
        self.layout.setSpacing(14)

        header = QVBoxLayout()
        title = QLabel("选品库")
        title.setObjectName("StudioTitle")
        subtitle = QLabel("查看当前账号最近 7 天的 AI 搜索选品结果")
        subtitle.setObjectName("Muted")
        header.addWidget(title)
        header.addWidget(subtitle)

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

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addLayout(header)
        left_layout.addWidget(self.attribute_box)
        list_header = QHBoxLayout()
        list_title = QLabel("我的搜索选品")
        list_title.setObjectName("StudioSectionTitle")
        self.list_title = list_title
        list_header.addWidget(list_title)
        list_header.addStretch()
        refresh_button = QPushButton()
        refresh_button.setObjectName("IconButton")
        refresh_button.setFixedSize(34, 34)
        refresh_button.setIcon(QIcon(icon_path("06_刷新图标.png")))
        refresh_button.setIconSize(QSize(17, 17))
        refresh_button.setToolTip("刷新商品数据")
        refresh_button.clicked.connect(self.force_refresh)
        self.data_refresh_button = refresh_button
        list_header.addWidget(refresh_button)
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
        for tab_name in ("选品分析报告", "人群匹配", "使用场景"):
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
        if not self.loaded:
            self.refresh_attributes()
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
        if not items:
            empty = QLabel("暂无搜索选品，请先在智能选品对话框提交需求。")
            empty.setObjectName("Muted")
            self.product_grid.addWidget(empty, 0, 0)
            return
        for index, item in enumerate(items):
            self.product_grid.addWidget(StudioNewProductCard(item, index, self._show_report), index // 6, index % 6)
        self.product_grid.setColumnStretch(6, 1)
        if items and not self.report_item:
            self._show_report(items[0])

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
        self.report_price.setText(format_jpy_price(price))
        sales = int(float(item.get("sales_count") or item.get("supplier_sales_count") or 0))
        score = item.get("weighted_score") or item.get("ai_score") or item.get("supplier_match_score") or 0
        self.report_summary.setText(f"销量 {sales:,} · AI 参考 {float(score):.0f} 分")
        self.report_image_layout.addWidget(create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140))
        title_key = str(item.get("title") or item.get("derived_title") or "")
        image_key = str(item.get("image_url") or item.get("supplier_image_url") or "")
        saved = next((favorite for favorite in self.favorite_items if favorite.get("title") == title_key and favorite.get("image_url") == image_key), None)
        self.favorite_button.setText("★  已在采集箱" if saved else "☆  加入采集箱")
        dimensions = dimension_items_from_report(item)
        if self.report_tab == "人群匹配":
            dimensions = [row for row in dimensions if row[0] in {"目标群体", "日本偏好", "竞品属性"}]
        elif self.report_tab == "使用场景":
            dimensions = [row for row in dimensions if row[0] in {"使用场景", "商品周期性", "复购属性"}]
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
        self.report_panel.hide()
        self.list_title.hide()
        self.data_refresh_button.hide()
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
            self.product_grid.addWidget(TeacherProductCard(item, self.open_derivable_product, can_derive=can_derive), index // 6, index % 6)
        self.product_grid.setColumnStretch(8, 1)

    def open_derivable_product(self, product: dict[str, Any]) -> None:
        dialog = DerivedDialog(self.gateway, product, [product], 0, self, review_mode=False)
        dialog.exec()
        self.refresh()

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
        items = self.favorite_items
        if not items:
            empty = QLabel("暂无采集商品，请在商品报告面板点击加入采集箱。")
            empty.setObjectName("Muted")
            self.product_grid.addWidget(empty, 0, 0)
            return
        listing = QTableWidget(0, 7)
        listing.setObjectName("CollectionTable")
        listing.setHorizontalHeaderLabels(["商品信息", "国家/地区", "商品分类", "价格", "销量", "1688 链接", "操作"])
        listing.verticalHeader().setVisible(False)
        listing.setShowGrid(False)
        listing.setAlternatingRowColors(True)
        listing.setSelectionBehavior(QAbstractItemView.SelectRows)
        listing.setSelectionMode(QAbstractItemView.NoSelection)
        listing.setEditTriggers(QAbstractItemView.NoEditTriggers)
        listing.setWordWrap(False)
        listing.setFocusPolicy(Qt.NoFocus)
        listing.cellClicked.connect(lambda row, column: self._show_report(items[row]) if 0 <= row < len(items) else None)
        header = listing.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 310)
        for column in range(1, 7):
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

            for column, value in ((1, region), (2, category)):
                label = QLabel(value)
                label.setObjectName("CollectionText")
                label.setAlignment(Qt.AlignCenter)
                listing.setCellWidget(row, column, label)

            price_label = QLabel(format_jpy_price(price))
            price_label.setObjectName("CollectionPrice")
            price_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 3, price_label)
            sales_label = QLabel(f"{int(float(sales or 0)):,}")
            sales_label.setObjectName("CollectionText")
            sales_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 4, sales_label)

            link_label = QLabel(f'<a href="{source_url}">打开链接</a>' if source_url else "暂无链接")
            link_label.setObjectName("CollectionLink")
            link_label.setOpenExternalLinks(bool(source_url))
            link_label.setAlignment(Qt.AlignCenter)
            listing.setCellWidget(row, 5, link_label)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)
            publish_button = QPushButton("加入上品")
            publish_button.setObjectName("CollectionAction")
            publish_button.clicked.connect(lambda checked=False, selected=item, url=source_url: self.add_to_publish(selected, url))
            export_button = QPushButton("导出报告")
            export_button.setObjectName("CollectionAction")
            export_button.clicked.connect(lambda checked=False, selected=item: self.export_collection_report(selected))
            actions_layout.addWidget(publish_button)
            actions_layout.addWidget(export_button)
            listing.setCellWidget(row, 6, actions)
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

    def export_collection_report(self, item: dict[str, Any]) -> None:
        title = str(item.get("title") or item.get("derived_title") or "商品")
        try:
            output_dir = APP_DIR / "data" / "selection_reports"
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_title = "".join(char for char in title[:24] if char not in '\\/:*?"<>|') or "商品"
            output_path = output_dir / f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            output_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "报告已导出", f"完整报告已保存：\n{output_path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))


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
        image = create_product_image(str(item.get("supplier_image_url") or item.get("image_url") or ""), "📦", 170, 140)
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
    def __init__(self, product: dict[str, Any], on_open, can_derive: bool = True) -> None:
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
        footer_layout.addWidget(self.generate_button)
        if next_button is not None:
            footer_layout.addWidget(next_button)
        layout.addWidget(footer)

        self.refresh_cards()

    def set_product(self, product: dict[str, Any]) -> None:
        self.product = product
        self.setWindowTitle(f"衍生品审核 - {str(self.product.get('title') or '')[:40]}")
        self._update_header()
        self.refresh_cards()

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
        self.generate_button.setEnabled(not bool(self.generation_task_id))

    def start_generation(self) -> None:
        try:
            result = self.gateway.start_product_full_pipeline(int(self.product["id"]))
            self.generation_task_id = int(result["task_id"])
            self.generation_progress.setValue(0)
            self.generation_progress.show()
            self.generate_button.setEnabled(False)
            self.generation_timer.start()
            self.product_progress.setText("正在执行：翻译、分族、衍生、1688匹配")
        except Exception as exc:
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
                self.generate_button.setEnabled(True)
                if task_failed:
                    QMessageBox.warning(self, "衍生失败", str(result.get("error_message") or result.get("message") or "任务失败"))
                else:
                    self.refresh_cards()
        except Exception as exc:
            self.generation_timer.stop()
            self.generation_task_id = None
            self.generation_progress.hide()
            self.generate_button.setEnabled(True)
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
            padding: 9px 16px; min-height: 34px; font-weight: 700; outline: 0;
        }
        QPushButton:focus { outline: 0; }
        QPushButton:hover { background: $accent_hover; }
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
        #CollectionLink { background: transparent; color: $accent; font-size: 12px; }
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
        #SideLoginButton:hover { background: $accent_hover; color: #ffffff; }
        #IconButton {
            background: $panel; color: $accent; border: 1px solid $border;
            border-radius: 8px; font-size: 13px; font-weight: 800;
        }
        #IconButton:hover { background: $accent; color: #ffffff; }
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
        #StudioPanelTitle { background: transparent; color: $text; font-size: 15px; font-weight: 900; }
        #StudioDot { background: transparent; color: #16a085; font-size: 16px; }
        #StudioPromptTitle { background: transparent; color: $text; font-size: 16px; font-weight: 800; }
        #StudioPromptHint { background: transparent; color: $muted; font-size: 13px; }
        #StudioModeCombo { min-width: 108px; min-height: 38px; padding: 0 24px 0 12px; color: $text; background: $panel; border: 1px solid $border; border-radius: 8px; }
        #StudioAnalyze { background: #16a085; color: #ffffff; border: 0; border-radius: 8px; min-width: 122px; min-height: 38px; font-weight: 800; }
        #StudioAnalyze:hover { background: #12866f; }
        #StudioPrimary {
            background: $accent; color: #ffffff; border: 0; border-radius: 8px;
            min-width: 112px; min-height: 38px; font-weight: 800;
        }
        #StudioPrimary:hover { background: $accent_hover; }
        #StudioSecondaryAction {
            background: $panel; color: $text; border: 1px solid $border;
            border-radius: 8px; min-height: 38px; font-weight: 800;
        }
        #StudioSecondaryAction:hover { color: $accent; border-color: $accent; }
        #StudioSecondaryAction:disabled, #StudioPrimary:disabled { color: $muted; background: $metric; }
        #RankFilterLabel { background: transparent; color: $text; font-size: 14px; font-weight: 700; padding-left: 2px; }
        #RankFilterPanel { background: transparent; border-bottom: 1px solid $border; }
        #RankFilterDate { background: $panel; color: $text; border: 1px solid $border; border-radius: 17px; padding: 7px 12px; font-size: 13px; font-weight: 700; }
        #RankFilterOption { background: transparent; color: $muted; border: 0; border-radius: 16px; padding: 7px 12px; min-height: 30px; font-size: 13px; }
        #RankFilterOption:hover { color: $accent; background: $tag; }
        #RankFilterOption:checked { color: #ffffff; background: $accent; font-weight: 800; }
        #RankFilterViewButton { background: $tag; color: $accent; border: 1px solid $border; border-radius: 8px; min-height: 32px; font-weight: 800; }
        #RankFilterViewButton:hover { background: $accent; color: #ffffff; }
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
        #StudioReportTitle { background: transparent; color: $text; font-size: 17px; font-weight: 900; line-height: 1.3; }
        #StudioDimension {
            background: $panel; border: 1px solid $border; border-radius: 8px;
        }
        #StudioDimensionName { background: transparent; color: $text; font-size: 13px; font-weight: 800; }
        #StudioDimensionGrade { background: transparent; color: $accent; font-size: 13px; font-weight: 800; }
        #StudioDimensionText { background: transparent; color: $muted; font-size: 13px; line-height: 1.25; }
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
        #StudioSummaryText { background: $panel; color: $muted; border-radius: 7px; padding: 7px 9px; font-size: 13px; }
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
        #SecondaryAction {
            background: $panel; color: $accent; border: 1px solid $accent;
            min-width: 130px;
        }
        #SecondaryAction:hover { background: $tag; }
        #ProductDeriveView {
            background: #4e75f6; min-width: 130px;
        }
        #ProductDeriveView:hover { background: #3d62d7; }
        #ProductDeriveAvailable {
            background: $accent; min-width: 130px;
        }
        #ProductDeriveAvailable:hover { background: $accent_hover; }
        #ProductDeriveDisabled {
            background: $metric; color: $muted; border: 1px solid $border; min-width: 130px;
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
