from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, ai, auth, pipeline, products, selection_attributes, suppliers, teacher
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
app.include_router(admin.router)
app.include_router(products.router)
app.include_router(selection_attributes.router)
app.include_router(ai.router)
app.include_router(teacher.router)
app.include_router(suppliers.router)
app.include_router(pipeline.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "tk-selection-backend"}
