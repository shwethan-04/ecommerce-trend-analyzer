"""
Database engine, session factory, and helper utilities.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Engine & session factory
# ------------------------------------------------------------------ #

# connect_args is only needed for SQLite (thread-safety)
_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ------------------------------------------------------------------ #
# Declarative base (shared by all models)
# ------------------------------------------------------------------ #

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ------------------------------------------------------------------ #
# Dependency / context-manager helpers
# ------------------------------------------------------------------ #

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session and ensures it is
    closed after the request completes.

    Usage::

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context-manager version of get_db for use outside FastAPI
    (e.g. CLI scripts, background tasks).

    Usage::

        with db_session() as db:
            products = db.query(Product).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Initialisation
# ------------------------------------------------------------------ #

def init_db() -> None:
    """
    Create all tables defined in the ORM models.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS semantics).
    """
    # Import models so that Base.metadata is populated before create_all
    from database import models  # noqa: F401  (side-effect import)

    logger.info("Initialising database at %s", settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialisation complete.")
