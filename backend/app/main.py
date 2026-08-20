import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import admin, ai, app_info, auth, auto_publish, dashboard, favorites, pipeline, products, regions, selection_attributes, suppliers, teacher, video
from app.core.database import BASE_DIR
from app.services.seed import init_db

app = FastAPI(title="TK Japan Selection MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(app_info.router)
app.include_router(admin.router)
app.include_router(products.router)
app.include_router(regions.router)
app.include_router(regions.admin_router)
app.include_router(selection_attributes.router)
app.include_router(ai.router)
app.include_router(teacher.router)
app.include_router(favorites.router)
app.include_router(dashboard.router)
app.include_router(auto_publish.router)
app.include_router(suppliers.router)
app.include_router(pipeline.router)
app.include_router(pipeline.selection_router)
app.include_router(video.router)
AUTO_PUBLISH_RUNTIME_DIR = BASE_DIR / "runtime" / "auto_publish"
AUTO_PUBLISH_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/auto_publish", StaticFiles(directory=AUTO_PUBLISH_RUNTIME_DIR), name="auto_publish")
RELEASE_RUNTIME_DIR = BASE_DIR / "runtime" / "releases"
RELEASE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/releases", StaticFiles(directory=RELEASE_RUNTIME_DIR), name="releases")
VIDEO_RUNTIME_DIR = BASE_DIR / "runtime" / "video_generation"
VIDEO_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/video_generation", StaticFiles(directory=VIDEO_RUNTIME_DIR), name="video_generation")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "tk-selection-backend"}

