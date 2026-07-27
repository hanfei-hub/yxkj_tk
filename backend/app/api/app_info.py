import os

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import AppRelease

router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/version")
def current_version(db: Session = Depends(get_db)):
    release = db.scalar(
        select(AppRelease)
        .where(AppRelease.status == 1)
        .order_by(AppRelease.published_at.desc(), AppRelease.id.desc())
    )
    if release:
        return {
            "version": release.version,
            "download_url": release.download_url,
            "release_notes": release.release_notes,
            "sha256": release.sha256,
            "force_update": bool(release.force_update),
        }
    return {
        "version": os.getenv("TK_APP_VERSION", "1.0.0"),
        "download_url": os.getenv("TK_APP_DOWNLOAD_URL", ""),
        "release_notes": os.getenv("TK_APP_RELEASE_NOTES", ""),
        "sha256": os.getenv("TK_APP_SHA256", ""),
        "force_update": os.getenv("TK_APP_FORCE_UPDATE", "0").lower() in {"1", "true", "yes"},
    }
