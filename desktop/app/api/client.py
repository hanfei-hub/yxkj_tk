from __future__ import annotations

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

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(str(exc)) from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if response.status_code == 401:
                detail = "请重新登录"
            raise ApiError(str(detail))
        if not response.text:
            return None
        return response.json()

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.request("POST", "/api/auth/login", {"username": username, "password": password})
        self.token = data["access_token"]
        return data

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, payload or {})

    def put(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("PUT", path, payload or {})

    def patch(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("PATCH", path, payload or {})
