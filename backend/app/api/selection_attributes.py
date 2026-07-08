from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.entities import SelectionAttribute
from app.services.serializers import attribute_to_dict

router = APIRouter(prefix="/api/selection-attributes", tags=["selection-attributes"])


class AttributeCreate(BaseModel):
    attribute_name: str
    attribute_code: str | None = None
    attribute_type: str = "other"
    description: str = ""
    default_weight: float = 1.0
    status: int = 1


@router.get("", dependencies=[Depends(require_role("admin", "teacher", "student"))])
def list_selection_attributes(db: Session = Depends(get_db)):
    items = db.scalars(
        select(SelectionAttribute)
        .where(SelectionAttribute.status == 1)
        .order_by(SelectionAttribute.id)
    ).all()
    return [attribute_to_dict(item) for item in items]


@router.post("", dependencies=[Depends(require_role("admin", "teacher"))])
def create_selection_attribute(
    payload: AttributeCreate,
    user: dict = Depends(require_role("admin", "teacher")),
    db: Session = Depends(get_db),
):
    attribute = SelectionAttribute(
        attribute_name=payload.attribute_name,
        attribute_code=payload.attribute_code or payload.attribute_name.lower().replace(" ", "_"),
        attribute_type=payload.attribute_type,
        description=payload.description,
        default_weight=payload.default_weight,
        current_weight=payload.default_weight,
        is_system=0,
        status=payload.status,
        created_by=user["id"],
    )
    db.add(attribute)
    db.commit()
    db.refresh(attribute)
    return attribute_to_dict(attribute)
