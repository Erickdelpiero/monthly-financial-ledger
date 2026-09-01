"""Shared test fixtures.

The suite runs against a REAL local PostgreSQL database (never SQLite, never
production). It is pointed at ``TEST_DATABASE_URL``; if that is unset every
test is skipped with an explanatory message.

The schema under test is built by running the actual Alembic migration to
``head`` — not ``Base.metadata.create_all`` — so the migration itself is
exercised on every run.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from money_ledger.models import EventType, Person, Transaction

REPO_ROOT = Path(__file__).resolve().parents[1]


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not set. Point it at a LOCAL, disposable "
            "PostgreSQL database (never production) — see README.md."
        )
    return url


def _make_alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    # Passed via attributes (a plain dict), not set_main_option — the latter
    # goes through configparser interpolation and breaks on a '%' in the URL.
    cfg.attributes["db_url"] = url
    return cfg


def _drop_everything(engine: Engine) -> None:
    """Best-effort clean slate for a throwaway database."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS transaction CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS person CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
        conn.execute(text("DROP FUNCTION IF EXISTS ledger_forbid_delete() CASCADE"))
        conn.execute(text("DROP FUNCTION IF EXISTS ledger_guard_update() CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS transaction_status"))
        conn.execute(text("DROP TYPE IF EXISTS event_type"))


@pytest.fixture(scope="session")
def database_url() -> str:
    return _require_test_database_url()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    return _make_alembic_config(database_url)


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Engine:
    eng = create_engine(database_url, future=True)
    _drop_everything(eng)
    command.upgrade(alembic_config, "head")
    yield eng
    _drop_everything(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Session:
    """Function-scoped session wrapped in an outer transaction that is always
    rolled back. ``join_transaction_mode="create_savepoint"`` keeps the outer
    transaction alive even when a test triggers (and recovers from) an
    IntegrityError.
    """
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Independent sessions that really commit — for concurrency / cross-txn tests.

    Tests using this are responsible for cleaning up the rows they commit.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


# --- data helpers -----------------------------------------------------------

def make_person(name: str = "Test Person", telegram_user_id: str | None = None) -> Person:
    return Person(
        name=name,
        telegram_user_id=telegram_user_id or f"tg-{uuid.uuid4()}",
    )


def make_transaction(
    created_by: Person,
    *,
    event_type: EventType = EventType.erick_gasta_para_mama,
    amount: Decimal = Decimal("35.50"),
    description: str = "taxi",
    event_date: date = date(2026, 8, 30),
    idempotency_key: str | None = None,
) -> Transaction:
    return Transaction(
        event_type=event_type,
        amount=amount,
        description=description,
        event_date=event_date,
        created_by=created_by,
        idempotency_key=idempotency_key or f"idem-{uuid.uuid4()}",
    )


@pytest.fixture()
def person(db_session: Session) -> Person:
    p = make_person()
    db_session.add(p)
    db_session.flush()
    return p


# --- API fixtures ---------------------------------------------------------

API_TOKEN = "test-api-token"


class RecordingLLM:
    """A stub LLM extractor that records every call, for API fallback tests."""

    def __init__(self, *, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def extract(self, raw_text: str):
        self.calls.append(raw_text)
        if self.error is not None:
            raise self.error
        return self.result


@contextlib.contextmanager
def build_api_client(database_url: str, engine: Engine, *, llm=None):
    """A TestClient over a real app on the test database. The app commits real
    rows, so the tables are truncated on exit.
    """
    from fastapi.testclient import TestClient

    from money_ledger.api import create_app

    app = create_app(database_url=database_url, api_token=API_TOKEN, llm=llm)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE transaction, person CASCADE"))


@pytest.fixture()
def api_client(database_url: str, engine: Engine):
    with build_api_client(database_url, engine) as client:
        yield client


@pytest.fixture()
def people(engine: Engine) -> dict[str, str]:
    """Two registered people, committed. Returns {'erick': <tg id>, 'mama': <tg id>}."""
    ids = {"erick": "tg-erick-001", "mama": "tg-mama-002"}
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        session.add(make_person(name="Erick", telegram_user_id=ids["erick"]))
        session.add(make_person(name="Mamá", telegram_user_id=ids["mama"]))
        session.commit()
    return ids
