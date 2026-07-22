from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_DIR = Path(__file__).resolve().parents[2]
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Configure the server MySQL connection before starting the backend.")
if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("SQLite is disabled. Use the server MySQL DATABASE_URL.")

engine_options = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
if DATABASE_URL.startswith(("mysql", "mariadb")):
    engine_options.update({"pool_size": 20, "max_overflow": 20, "pool_timeout": 60})

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
