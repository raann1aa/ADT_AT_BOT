"""
Database Connection and Session Management.
Supports PostgreSQL for production and SQLite for local development and testing.
Uses SQLAlchemy 2.0 ORM DeclarativeBase and thread-safe session pooling.
"""

import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool

logger = logging.getLogger("Database")

# Determine base directory and default SQLite database path
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "krishibot.db"

# Retrieve DATABASE_URL from environment or fallback to SQLite
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")

# Database configuration options
DB_ECHO = os.getenv("DB_ECHO", "false").lower() in ("true", "1", "yes")

def get_engine_args(url: str):
    """Generates appropriate engine arguments based on dialect (PostgreSQL vs SQLite)."""
    if url.startswith("sqlite"):
        engine_args = {
            "connect_args": {"check_same_thread": False},
            "echo": DB_ECHO,
        }
        # For in-memory SQLite (e.g. testing), use StaticPool
        if ":memory:" in url:
            engine_args["poolclass"] = StaticPool
        return engine_args
    else:
        # PostgreSQL / Production settings
        pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))
        return {
            "poolclass": QueuePool,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": True,
            "echo": DB_ECHO,
        }

# Ensure data directory exists if using local SQLite file
if DATABASE_URL.startswith("sqlite") and ":memory:" not in DATABASE_URL:
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    Path(db_file_path).parent.mkdir(parents=True, exist_ok=True)

# Create Engine
engine = create_engine(DATABASE_URL, **get_engine_args(DATABASE_URL))

# Enforce foreign key constraints for SQLite connections
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Session Factory
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

# SQLAlchemy 2.0 Base
Base = declarative_base()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for transactional database sessions."""
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    session: Session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Initializes database schema and ensures all declared tables exist."""
    import database.models  # Ensure models are imported so Base.metadata is populated
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")


def check_connection() -> bool:
    """Verifies that the database is reachable and accepting queries."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connectivity check failed: {e}")
        return False
