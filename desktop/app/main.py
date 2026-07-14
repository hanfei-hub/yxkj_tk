from __future__ import annotations

import sys
import json
from io import BytesIO
from pathlib import Path
from string import Template
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QPixmap
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

    def sync_fastmoss_products(self) -> dict[str, Any]:
        return self.client.post("/api/fastmoss/sync-products?page=1&pagesize=20")

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

    def ai_chat(self, message: str) -> str:
        return self.client.post("/api/ai/chat-selection", {"message": message})["answer"]

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

    def setup_pages(self) -> None:
        self.add_page("智能选品", StudentSelectionPage(self.gateway), "01_智能选品.ico")
        self.add_page("教师看板", TeacherDashboardPage(self.gateway), "02_教师看板.ico")
        self.add_page("任务看板", PipelinePage(self.gateway), "07_第三方API.ico")
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
            self.user_avatar.setText(real_name[:1].upper())
            self.user_name.setText(real_name)
            self.user_role.setText(role_map.get(role, role or "已登录"))
            self.user_status.setText(f"后端在线 · {api_host}")
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
    def __init__(self, item: dict[str, Any], index: int) -> None:
        super().__init__()
        self.setObjectName("CompactProductCard")
        self.setFixedSize(148, 242)

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
        send = QPushButton("🚀 开始选品")
        send.setObjectName("PrimaryAction")
        send.clicked.connect(self.send_chat)
        row.addWidget(self.chat_input, 1)
        row.addWidget(send)
        chat_layout.addLayout(row)

        self.layout.addWidget(chat_box)

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

    def send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        answer = self.gateway.ai_chat(text)
        QMessageBox.information(self, "AI 选品结果", answer)
        self.chat_input.clear()

    def refresh(self) -> None:
        while self.product_row.count():
            child = self.product_row.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        while self.new_product_grid.count():
            child = self.new_product_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        derived_items = self.load_card_items()
        new_items = self.load_new_items()
        if not derived_items:
            empty = QLabel("暂无衍生品，先在任务看板补齐衍生品。")
            empty.setObjectName("Muted")
            self.product_row.addWidget(empty)
        else:
            for index, item in enumerate(derived_items):
                self.product_row.addWidget(CompactProductCard(item, index))
        self.product_row.addStretch()
        content_width = max(1, len(derived_items)) * 148 + max(0, len(derived_items) - 1) * 10 + 8
        self.product_content.setFixedWidth(content_width)
        self.product_content.setFixedHeight(252)
        columns = 6
        self.new_product_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        for index, item in enumerate(new_items):
            self.new_product_grid.addWidget(ProductCard(item, index), index // columns, index % columns)
        self.new_product_grid.setColumnStretch(columns, 1)
        rows = max(1, (len(new_items) + columns - 1) // columns)
        self.new_product_content.setMinimumHeight(rows * 386 + 24)

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
        names = [
            ("dimension_1", "使用场景"),
            ("dimension_2", "商品周期性"),
            ("dimension_3", "目标群体"),
            ("dimension_4", "短视频种草"),
            ("dimension_5", "日本偏好"),
            ("dimension_6", "新奇特"),
            ("dimension_7", "复购属性"),
            ("dimension_8", "竞品属性"),
        ]
        raw_report = item.get("analysis_report") or {}
        if isinstance(raw_report, str):
            try:
                raw_report = json.loads(raw_report)
            except (TypeError, ValueError):
                raw_report = {}
        result: list[tuple[str, str, str]] = []
        for code, default_name in names:
            row = raw_report.get(code) if isinstance(raw_report, dict) else None
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

