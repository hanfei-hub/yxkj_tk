from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


class ApiError(RuntimeError):
    pass


@dataclass
class ApiClient:
    base_url: str = os.getenv("TK_SELECTION_API_BASE_URL", "http://120.26.207.89:8000")
    token: str | None = None
    timeout: int = 180

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int | None = None) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers(),
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(f"网络请求失败\n请求：{method} {path}\n异常：{type(exc).__name__}: {exc}") from exc

        if response.status_code >= 400:
            raw_text = (response.text or "").strip()
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                detail = body.get("detail") or body.get("message") or body.get("msg") or body
            else:
                detail = raw_text
            if isinstance(detail, (dict, list)):
                detail = json.dumps(detail, ensure_ascii=False, indent=2)
            detail = str(detail).strip() or "服务器没有返回错误正文"
            if response.status_code == 401:
                detail = "请重新登录\n" + detail
            raise ApiError(
                f"HTTP {response.status_code} {response.reason}\n"
                f"请求：{method} {path}\n"
                f"响应：{detail}"
            )
        if not response.text:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(
                f"响应解析失败\n请求：{method} {path}\n"
                f"HTTP {response.status_code}\n响应正文：{response.text[:2000]}"
            ) from exc

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.request("POST", "/api/auth/login", {"username": username, "password": password})
        self.token = data["access_token"]
        return data

    def get(self, path: str, timeout: int | None = None) -> Any:
        return self.request("GET", path, timeout=timeout)

    def post(self, path: str, payload: dict[str, Any] | None = None, timeout: int | None = None) -> Any:
        return self.request("POST", path, payload or {}, timeout=timeout)

    def put(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("PUT", path, payload or {})

    def patch(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("PATCH", path, payload or {})

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
