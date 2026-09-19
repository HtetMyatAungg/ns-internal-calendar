"""Database connection helpers.

Usage:

    from core.db import session_scope

    with session_scope() as db:
        db.add(Member(...))
    # committed automatically; rolled back on exception
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings, load_settings
from core.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def normalize_url(url: str) -> str:
    """Make sure SQLAlchemy uses the psycopg (v3) driver.

    Hosted providers (Neon, Supabase, Render, ...) hand out URLs that start with
    `postgres://` or `postgresql://`; SQLAlchemy needs `postgresql+psycopg://`.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        settings = settings or load_settings()
        _engine = create_engine(
            normalize_url(settings.database_url),
            pool_pre_ping=True,
            # Server-side prepared statements buy little here and break on
            # connection poolers / PGlite that share one backend session.
            connect_args={"prepare_threshold": None},
        )
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Dispose the current engine (used by tests to switch databases)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _SessionFactory is not None
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(settings: Settings | None = None) -> None:
    """Create tables if missing and make sure configured admins can log in."""
    from core.services import ensure_admins

    settings = settings or load_settings()
    Base.metadata.create_all(get_engine(settings))
    ensure_admins(settings.admin_emails)
