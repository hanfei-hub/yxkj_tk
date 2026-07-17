from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL")
BASE_DIR = Path(__file__).resolve().parents[2]
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Configure the server MySQL connection before starting backend.")

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("SQLite is no longer supported for this project. Use the server MySQL DATABASE_URL.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
