import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "50"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "100"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

if DB_URL.startswith("sqlite"):
    # Use NullPool to avoid pool exhaustion with sqlite; each session gets a fresh connection
    engine = create_engine(
        DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
else:
    engine = create_engine(
        DB_URL,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
