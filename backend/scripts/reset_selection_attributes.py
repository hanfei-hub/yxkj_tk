from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models.entities import DerivedProductAttributeScore, SelectionAttribute  # noqa: E402
from app.services.product_family_service import DIMENSIONS, INITIAL_WEIGHT  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        db.execute(delete(DerivedProductAttributeScore))
        db.execute(delete(SelectionAttribute))
        db.flush()

        if engine.dialect.name != "mysql":
            raise RuntimeError(f"Unsupported database dialect: {engine.dialect.name}")
        db.execute(text("ALTER TABLE selection_attributes AUTO_INCREMENT = 1"))

        for index, (code, name) in enumerate(DIMENSIONS, start=1):
            db.add(
                SelectionAttribute(
                    id=index,
                    attribute_name=name,
                    attribute_code=code,
                    attribute_type="dimension",
                    description=f"衍生品审核维度：{name}",
                    default_weight=INITIAL_WEIGHT,
                    current_weight=INITIAL_WEIGHT,
                    is_system=1,
                    status=1,
                )
            )

        db.commit()

        rows = db.scalars(select(SelectionAttribute).order_by(SelectionAttribute.id)).all()
        print(f"selection_attributes_count={len(rows)}")
        for row in rows:
            print(f"{row.id}\t{row.attribute_code}\t{row.attribute_name}\t{row.current_weight}")


if __name__ == "__main__":
    main()
