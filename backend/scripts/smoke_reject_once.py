from __future__ import annotations

import sys
from pathlib import Path

import requests
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.entities import ProductFamilyDimensionWeight  # noqa: E402


BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    session = requests.Session()
    response = session.post(BASE_URL + "/api/auth/login", json={"username": "admin", "password": "admin123"}, timeout=30)
    response.raise_for_status()
    session.headers.update({"Authorization": "Bearer " + response.json()["access_token"]})

    products = session.get(BASE_URL + "/api/products/hot", timeout=30).json()
    if not products:
        raise RuntimeError("no product to reject")
    derived = session.get(BASE_URL + f"/api/teacher/products/{products[0]['id']}/derived-products", timeout=30).json()
    if not derived:
        raise RuntimeError("no derived product to reject")
    attrs = session.get(BASE_URL + "/api/selection-attributes", timeout=30).json()
    if not attrs:
        raise RuntimeError("no selection attribute")

    response = session.post(
        BASE_URL + f"/api/teacher/derived-products/{derived[0]['id']}/reject",
        json={"attribute_ids": [attrs[0]["id"]], "review_comment": "自动测试：中文衍生品拒绝"},
        timeout=30,
    )
    response.raise_for_status()
    print("reject_status", response.json().get("item", {}).get("review_status"))

    with SessionLocal() as db:
        for row in db.scalars(select(ProductFamilyDimensionWeight).order_by(ProductFamilyDimensionWeight.dimension_code)).all():
            print(row.dimension_code, row.dimension_name, row.weight_percent, row.reject_count, row.total_review_count)


if __name__ == "__main__":
    main()
