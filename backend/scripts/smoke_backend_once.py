from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import delete, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models.entities import (  # noqa: E402
    DailyRecommendation,
    DerivedProductAttributeScore,
    DerivedProductDimensionReport,
    DerivedProductRecommendation,
    FastMossSyncLog,
    FmProduct,
    ProductFamily,
    ProductFamilyDimensionWeight,
    TeacherReviewRecord,
)


BASE_URL = "http://127.0.0.1:8000"


def clear_business_data() -> None:
    business_tables = [
        TeacherReviewRecord,
        DerivedProductDimensionReport,
        DerivedProductAttributeScore,
        DailyRecommendation,
        DerivedProductRecommendation,
        FastMossSyncLog,
        FmProduct,
        ProductFamilyDimensionWeight,
        ProductFamily,
    ]
    with SessionLocal() as db:
        for model in business_tables:
            db.execute(delete(model))
        db.flush()
        if engine.dialect.name == "mysql":
            for model in business_tables:
                db.execute(text(f"ALTER TABLE {model.__tablename__} AUTO_INCREMENT = 1"))
        db.commit()
    print("business_data_cleared")


def main() -> None:
    clear_business_data()

    session = requests.Session()
    response = session.post(BASE_URL + "/api/auth/login", json={"username": "admin", "password": "admin123"}, timeout=30)
    response.raise_for_status()
    session.headers.update({"Authorization": "Bearer " + response.json()["access_token"]})
    print("login_ok")

    start = time.time()
    response = session.post(BASE_URL + "/api/fastmoss/sync-products?page=1&pagesize=1", json={}, timeout=240)
    print("sync_status", response.status_code, "elapsed", round(time.time() - start, 2))
    print(json.dumps(response.json(), ensure_ascii=False)[:2000])
    response.raise_for_status()

    for index in range(24):
        time.sleep(2 if index == 0 else 10)
        status = session.get(BASE_URL + "/api/pipeline/status", timeout=30).json()
        derived_count = int(status.get("derivation", {}).get("derived_count") or 0)
        print("poll", index + 1, "derived_count", derived_count)
        if derived_count >= 10:
            break

    products = session.get(BASE_URL + "/api/products/hot", timeout=30).json()
    print("product_count", len(products))
    if not products:
        raise RuntimeError("no products after FastMoss sync")
    print("product_title", products[0].get("title"))

    derived = session.get(BASE_URL + f"/api/teacher/products/{products[0]['id']}/derived-products", timeout=30).json()
    print("derived_count", len(derived))
    if not derived:
        raise RuntimeError("no derived products generated")

    for item in derived[:3]:
        print("derived", item.get("id"), item.get("derived_title"), "|", item.get("usage_scene"))
        try:
            report = json.loads(item.get("analysis_report") or "{}")
        except ValueError:
            report = {}
        print("dimension_1", json.dumps(report.get("dimension_1") or {}, ensure_ascii=False))


if __name__ == "__main__":
    main()
