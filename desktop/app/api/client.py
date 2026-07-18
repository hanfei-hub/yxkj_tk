from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class ApiError(RuntimeError):
    pass


def format_error_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail or "Request failed"
    if isinstance(detail, list):
        messages: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
                msg = item.get("msg") or item.get("message") or item.get("detail") or item
                messages.append(f"{loc}: {msg}" if loc else str(msg))
            else:
                messages.append(str(item))
        return "\n".join(messages) or "Request parameter error"
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("error") or detail.get("detail") or detail)
    return str(detail or "Request failed")


@dataclass
class ApiClient:
    base_url: str = os.getenv("TK_SELECTION_API_BASE_URL", "http://127.0.0.1:8000")
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
            raise ApiError(f"Network request failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", body)
            except ValueError:
                detail = response.text
            if response.status_code == 401:
                detail = "Please log in again"
            message = format_error_detail(detail)
            raise ApiError(f"HTTP {response.status_code}: {message}")
        if not response.text:
            return None
        return response.json()

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
