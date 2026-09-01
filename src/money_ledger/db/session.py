"""Engine / session factories.

Block 1 keeps this deliberately thin: no global engine is created at import
time (that would fail whenever DATABASE_URL is unset). Callers build an engine
explicitly.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from money_ledger.config import get_database_url


def build_engine(url: str | None = None, **kwargs) -> Engine:
    return create_engine(url or get_database_url(), pool_pre_ping=True, future=True, **kwargs)


def build_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
