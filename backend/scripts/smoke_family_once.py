from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.entities import ProductFamily  # noqa: E402
from app.services.product_family_service import get_or_create_product_family  # noqa: E402


def main() -> None:
    title = "会爬会动的螃蟹电动感应儿童玩具1一2岁吸引宝宝注意力"
    category = "母婴玩具 / 婴幼儿玩具"
    with SessionLocal() as db:
        before_count = len(db.scalars(select(ProductFamily)).all())
        family = get_or_create_product_family(db, title=title, category=category)
        db.commit()
        after_count = len(db.scalars(select(ProductFamily)).all())
        print("before_count", before_count)
        print("after_count", after_count)
        print("family_id", family.id)
        print("family_group", family.family_group)
        print("family_variant", family.family_variant)
        print("family_name", family.family_name)
        print("normalized_keywords", family.normalized_keywords)
        print("match_rule", family.match_rule)


if __name__ == "__main__":
    main()
