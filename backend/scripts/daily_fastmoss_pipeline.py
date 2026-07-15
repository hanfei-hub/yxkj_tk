from __future__ import annotations

import json

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import FmProduct
from app.services.fastmoss_service import get_fastmoss_config, request_new_listed, upsert_new_listed_products
from app.services.selection_derivation_service import generate_derivatives_for_product_ids


def main() -> None:
    page = 1
    page_size = 50
    with SessionLocal() as db:
        config = get_fastmoss_config(db)
        raw = request_new_listed(config, page=page, page_size=page_size)
        stats = upsert_new_listed_products(db, raw)
        request_date = str(raw.get("request", {}).get("filter", {}).get("date_info", {}).get("value", ""))
        product_ids = list(
            db.scalars(
                select(FmProduct.id)
                .where(FmProduct.platform == "TikTok", FmProduct.list_type == "new", FmProduct.data_date == request_date)
                .order_by(FmProduct.rank_no, FmProduct.id)
                .limit(page_size)
            ).all()
        )
    derivation_result = generate_derivatives_for_product_ids(product_ids) if product_ids else {"generated_count": 0, "errors": []}
    print(
        json.dumps(
            {
                "synced": stats,
                "request_date": request_date,
                "product_count": len(product_ids),
                "derivation": derivation_result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
