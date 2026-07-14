from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QMessageBox, QPushButton, QTableWidget  # noqa: E402

from app.main import DerivedDialog, MainWindow, RejectDialog, apply_style  # noqa: E402
from app.api.client import ApiClient  # noqa: E402


class FakeGateway:
    def __init__(self) -> None:
        self.offline = False
        self.user = {"id": 1, "username": "admin", "real_name": "系统管理员", "role": "admin", "status": 1}
        self.client = ApiClient(base_url="http://test.local")
        self.calls: list[str] = []
        self._users = [
            {"id": 1, "username": "admin", "real_name": "系统管理员", "role": "admin", "status": 1, "last_login_at": "-"}
        ]
        self._models = [
            {
                "id": 5,
                "config_name": "deepseekV1",
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "has_api_key": True,
                "model_name": "deepseek-chat",
                "status": 1,
                "is_default": 1,
            }
        ]
        self._third = [
            {"id": 1, "config_name": "FastMoss 日本区 API", "service_type": "fastmoss", "status": 1}
        ]
        self._attrs = [
            {"id": 1, "attribute_name": "使用场景", "attribute_code": "dimension_1", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 2, "attribute_name": "商品周期性", "attribute_code": "dimension_2", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 3, "attribute_name": "目标群体", "attribute_code": "dimension_3", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 4, "attribute_name": "短视频流量种草适配能力", "attribute_code": "dimension_4", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 5, "attribute_name": "日本市场偏好", "attribute_code": "dimension_5", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 6, "attribute_name": "是否属于新奇特商品", "attribute_code": "dimension_6", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 7, "attribute_name": "复购属性", "attribute_code": "dimension_7", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
            {"id": 8, "attribute_name": "竞品属性", "attribute_code": "dimension_8", "attribute_type": "dimension", "current_weight": 12.5, "status": 1},
        ]
        self._products = [
            {
                "id": 1,
                "title": "萌宠动物园系列 解压史莱姆玩具",
                "image_url": "",
                "price": 3167,
                "sales_count": 372,
                "rank_no": 1,
                "category": "玩具",
                "derived_count": 10,
                "pending_count": 10,
            },
            {
                "id": 2,
                "title": "动物造型解压捏捏乐",
                "image_url": "",
                "price": 1200,
                "sales_count": 90,
                "rank_no": 2,
                "category": "玩具",
                "derived_count": 0,
                "pending_count": 0,
            },
        ]
        self._derived = [
            {
                "id": 1,
                "source_product_id": 1,
                "derived_title": "动物造型解压捏捏乐",
                "usage_scene": "办公桌、学习间隙、通勤途中",
                "target_audience": "学生、上班族",
                "recommendation_reason": "捏压回弹有展示效果。",
                "risk_notes": "需确认材质安全。",
                "weighted_score": 86,
                "review_status": "pending",
                "analysis_report": json.dumps(
                    {
                        "dimension_1": {"dimension_name": "使用场景", "rating_level": "高", "analysis_content": "多场景可用。"},
                        "dimension_2": {"dimension_name": "商品周期性", "rating_level": "中", "analysis_content": "全年可卖。"},
                        "dimension_3": {"dimension_name": "目标群体", "rating_level": "高", "analysis_content": "学生和上班族。"},
                        "dimension_4": {"dimension_name": "短视频流量种草适配能力", "rating_level": "高", "analysis_content": "视觉反馈明确。"},
                        "dimension_5": {"dimension_name": "日本市场偏好", "rating_level": "中", "analysis_content": "可爱小物方向。"},
                        "dimension_6": {"dimension_name": "是否属于新奇特商品", "rating_level": "中", "analysis_content": "造型差异化。"},
                        "dimension_7": {"dimension_name": "复购属性", "rating_level": "低", "analysis_content": "个人复购弱。"},
                        "dimension_8": {"dimension_name": "竞品属性", "rating_level": "中", "analysis_content": "同类较多。"},
                    },
                    ensure_ascii=False,
                ),
            }
        ]

    def _call(self, name: str) -> None:
        self.calls.append(name)

    def is_invalid_token_error(self, exc: Exception) -> bool:
        return "token" in str(exc).lower() or "重新登录" in str(exc)

    def clear_session(self) -> None:
        self._call("clear_session")

    def login(self, username: str, password: str) -> dict[str, Any]:
        self._call("login")
        return self.user

    def hot_products(self) -> list[dict[str, Any]]:
        self._call("hot_products")
        return list(self._products)

    def daily_recommendations(self) -> list[dict[str, Any]]:
        self._call("daily_recommendations")
        return list(self._products)

    def recommended_derived_products(self, limit: int = 10) -> list[dict[str, Any]]:
        self._call("recommended_derived_products")
        return list(self._derived[:limit])

    def derived_products(self, product_id: int) -> list[dict[str, Any]]:
        self._call(f"derived_products:{product_id}")
        return list(self._derived if product_id == 1 else [])

    def attributes(self) -> list[dict[str, Any]]:
        self._call("attributes")
        return list(self._attrs)

    def users(self) -> list[dict[str, Any]]:
        self._call("users")
        return list(self._users)

    def model_configs(self) -> list[dict[str, Any]]:
        self._call("model_configs")
        return list(self._models)

    def third_party_configs(self) -> list[dict[str, Any]]:
        self._call("third_party_configs")
        return list(self._third)

    def pipeline_status(self) -> dict[str, Any]:
        self._call("pipeline_status")
        return {
            "fastmoss": {"product_count": 1, "latest_sync": {"status": "success", "request_date": "2026-07-08", "translation_success_count": 1}},
            "families": {"family_count": 1},
            "derivation": {"derived_count": 10, "products_without_enough_derivatives": 0},
            "supplier_1688": {"matched_count": 0, "status_counts": {"not_searched": 10}},
            "review": {"review_record_count": 0, "status_counts": {"pending": 10}},
        }

    def queue_pending_derivations(self, limit: int = 5, min_derived_count: int = 10) -> dict[str, Any]:
        self._call("queue_pending_derivations")
        return {"ok": True, "queued_count": 1}

    def queue_supplier_matches(self, limit: int = 5, threshold: float = 90, max_candidates: int = 200, page_size: int = 20) -> dict[str, Any]:
        self._call("queue_supplier_matches")
        return {"ok": True, "queued": True}

    def ai_chat(self, message: str) -> str:
        self._call("ai_chat")
        return "测试 AI 回复"

    def sync_fastmoss_products(self) -> dict[str, Any]:
        self._call("sync_fastmoss_products")
        return {"message": "测试同步完成", "synced_count": 1, "total_count": 1}

    def set_default_model(self, config_id: int) -> dict[str, Any]:
        self._call("set_default_model")
        return {"ok": True}

    def set_model_status(self, config_id: int, status: int) -> dict[str, Any]:
        self._call("set_model_status")
        return {"ok": True}

    def set_third_party_status(self, config_id: int, status: int) -> dict[str, Any]:
        self._call("set_third_party_status")
        return {"ok": True}

    def set_attribute_status(self, attribute_id: int, status: int) -> dict[str, Any]:
        self._call("set_attribute_status")
        return {"ok": True}

    def set_user_status(self, user_id: int, status: int) -> dict[str, Any]:
        self._call("set_user_status")
        return {"ok": True}

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._call("create_user")
        return {"id": 2}

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._call("update_user")
        return {"ok": True}

    def save_model_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        self._call("save_model_config")
        return {"id": config_id or 99}

    def save_third_party_config(self, payload: dict[str, Any], config_id: int | None = None) -> dict[str, Any]:
        self._call("save_third_party_config")
        return {"id": config_id or 99}

    def save_attribute(self, payload: dict[str, Any], attribute_id: int | None = None) -> dict[str, Any]:
        self._call("save_attribute")
        return {"id": attribute_id or 99}

    def reject(self, derived_id: int, attribute_ids: list[int], comment: str) -> None:
        self._call("reject")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    apply_style(app, "light")
    gateway = FakeGateway()

    message_count = {"info": 0, "warning": 0}
    original_info = QMessageBox.information
    original_warning = QMessageBox.warning
    original_exec = QDialog.exec

    def fake_info(*args: Any, **kwargs: Any) -> QMessageBox.StandardButton:
        message_count["info"] += 1
        return QMessageBox.StandardButton.Ok

    def fake_warning(*args: Any, **kwargs: Any) -> QMessageBox.StandardButton:
        message_count["warning"] += 1
        return QMessageBox.StandardButton.Ok

    def fake_exec(self: QDialog) -> int:
        return int(QDialog.DialogCode.Rejected)

    QMessageBox.information = fake_info  # type: ignore[method-assign]
    QMessageBox.warning = fake_warning  # type: ignore[method-assign]
    QDialog.exec = fake_exec  # type: ignore[method-assign]

    errors: list[str] = []
    clicked: list[str] = []
    try:
        window = MainWindow(gateway)
        QApplication.processEvents()

        for index in range(window.stack.count()):
            window.nav.setCurrentRow(index)
            QApplication.processEvents()
            clicked.append(f"nav:{index}")

        student = window.stack.widget(0)
        teacher = window.stack.widget(1)
        pipeline = window.stack.widget(2)
        users = window.stack.widget(3)
        models = window.stack.widget(4)
        third = window.stack.widget(5)
        attrs = window.stack.widget(6)
        theme_page = window.stack.widget(7)

        method_calls = [
            ("login_dialog", window.open_login_dialog),
            ("student_refresh", student.force_refresh),
            ("student_scroll", student.scroll_products_next),
            ("teacher_refresh", teacher.force_refresh),
            ("pipeline_refresh", pipeline.refresh),
            ("pipeline_queue_derivations", pipeline.queue_derivations),
            ("pipeline_queue_supplier_matches", pipeline.queue_supplier_matches),
            ("users_add", users.add_user),
            ("models_add", models.add_config),
            ("third_add", third.add_config),
            ("attrs_add", attrs.add_attribute),
        ]
        student.chat_input.setText("测试选品")
        method_calls.append(("student_send_chat", student.send_chat))
        for table in users.findChildren(QTableWidget):
            if table.rowCount() > 0:
                table.selectRow(0)
        for table in models.findChildren(QTableWidget):
            if table.rowCount() > 0:
                table.selectRow(0)
        for table in third.findChildren(QTableWidget):
            if table.rowCount() > 0:
                table.selectRow(0)
        for table in attrs.findChildren(QTableWidget):
            if table.rowCount() > 0:
                table.selectRow(0)
        method_calls.extend(
            [
                ("users_edit", users.edit_user),
                ("users_toggle", users.toggle_user),
                ("models_edit", models.edit_config),
                ("models_toggle", models.toggle_config),
                ("models_default", models.set_default),
                ("third_edit", third.edit_config),
                ("third_toggle", third.toggle_config),
                ("third_sync_fastmoss", third.sync_fastmoss),
                ("attrs_edit", attrs.edit_attribute),
                ("attrs_toggle", attrs.toggle_attribute),
            ]
        )

        for label, method in method_calls:
            try:
                method()
                QApplication.processEvents()
                clicked.append(label)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{label}:{exc}")

        combo = theme_page.findChild(QComboBox)
        if combo:
            for idx in range(combo.count()):
                combo.setCurrentIndex(idx)
                QApplication.processEvents()
                clicked.append(f"theme:{idx}")

        dialog = DerivedDialog(gateway, gateway._products[0], gateway._products, 0)
        dialog.next_product()
        dialog.next_product()
        for button in dialog.findChildren(QPushButton):
            try:
                button.click()
                QApplication.processEvents()
                clicked.append(f"derived_dialog:{button.text()}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"derived_dialog:{button.text()}:{exc}")

        reject_dialog = RejectDialog(gateway, gateway._derived[0])
        reject_dialog.submit()
        QApplication.processEvents()
        clicked.append("reject_dialog:确认拒绝")

        print("clicked_count", len(clicked))
        print("messages", message_count)
        print("gateway_calls", sorted(set(gateway.calls)))
        if errors:
            print("errors")
            for error in errors:
                print(error)
            return 1
        print("ui_button_smoke_ok")
        return 0
    finally:
        QMessageBox.information = original_info  # type: ignore[method-assign]
        QMessageBox.warning = original_warning  # type: ignore[method-assign]
        QDialog.exec = original_exec  # type: ignore[method-assign]
        QTimer.singleShot(0, app.quit)


if __name__ == "__main__":
    raise SystemExit(main())
