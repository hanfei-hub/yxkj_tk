from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.entities import RegionConfig
from app.services.serializers import region_to_dict


router = APIRouter(prefix="/api/regions", tags=["regions"])
admin_router = APIRouter(
    prefix="/api/admin/regions",
    tags=["admin-regions"],
    dependencies=[Depends(require_role("admin"))],
)


class RegionPayload(BaseModel):
    region_name: str
    region_code: str
    status: int = 1
    sort_order: int = 0


@router.get("")
def list_active_regions(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    items = db.scalars(
        select(RegionConfig)
        .where(RegionConfig.status == 1)
        .order_by(RegionConfig.sort_order, RegionConfig.id)
    ).all()
    return [region_to_dict(item) for item in items]


@admin_router.get("")
def list_regions(db: Session = Depends(get_db)):
    items = db.scalars(select(RegionConfig).order_by(RegionConfig.sort_order, RegionConfig.id)).all()
    return [region_to_dict(item) for item in items]


@admin_router.post("")
def create_region(payload: RegionPayload, db: Session = Depends(get_db)):
    code = payload.region_code.strip().upper()
    name = payload.region_name.strip()
    if not name or not code:
        raise HTTPException(status_code=400, detail="国家/地区名称和代码不能为空")
    if db.scalar(select(RegionConfig).where(RegionConfig.region_code == code)):
        raise HTTPException(status_code=400, detail="该地区代码已存在")
    item = RegionConfig(region_name=name, region_code=code, status=payload.status, sort_order=payload.sort_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return region_to_dict(item)


@admin_router.put("/{region_id}")
def update_region(region_id: int, payload: RegionPayload, db: Session = Depends(get_db)):
    item = db.get(RegionConfig, region_id)
    if not item:
        raise HTTPException(status_code=404, detail="国家/地区不存在")
    code = payload.region_code.strip().upper()
    name = payload.region_name.strip()
    duplicate = db.scalar(select(RegionConfig).where(RegionConfig.region_code == code, RegionConfig.id != region_id))
    if not name or not code:
        raise HTTPException(status_code=400, detail="国家/地区名称和代码不能为空")
    if duplicate:
        raise HTTPException(status_code=400, detail="该地区代码已存在")
    item.region_name = name
    item.region_code = code
    item.status = payload.status
    item.sort_order = payload.sort_order
    db.commit()
    db.refresh(item)
    return region_to_dict(item)


@admin_router.patch("/{region_id}/status")
def set_region_status(region_id: int, payload: dict, db: Session = Depends(get_db)):
    item = db.get(RegionConfig, region_id)
    if not item:
        raise HTTPException(status_code=404, detail="国家/地区不存在")
    item.status = 1 if int(payload.get("status", 1)) else 0
    db.commit()
    return region_to_dict(item)


@admin_router.delete("/{region_id}")
def delete_region(region_id: int, db: Session = Depends(get_db)):
    item = db.get(RegionConfig, region_id)
    if not item:
        raise HTTPException(status_code=404, detail="国家/地区不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "deleted_id": region_id}

