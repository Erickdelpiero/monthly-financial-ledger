"""Idempotency is guaranteed by a database-level UNIQUE constraint.

PHASE-2.6 §7.1 / PHASE-2.9 §6: a SELECT-then-INSERT check is NOT sufficient on
its own; PostgreSQL must reject the duplicate atomically.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from money_ledger.models import EventType, Transaction
from tests.conftest import make_person, make_transaction


def test_unique_constraint_on_idempotency_key_exists_in_schema(engine: Engine) -> None:
    insp = inspect(engine)
    uniques = insp.get_unique_constraints("transaction")
    indexes = insp.get_indexes("transaction")

    via_constraint = any(u["column_names"] == ["idempotency_key"] for u in uniques)
    via_unique_index = any(
        ix["column_names"] == ["idempotency_key"] and ix.get("unique")
        for ix in indexes
    )
    assert via_constraint or via_unique_index, (
        "transaction.idempotency_key must be UNIQUE at the database level"
    )
    assert any(u["name"] == "uq_transaction_idempotency_key" for u in uniques)


def test_duplicate_idempotency_key_rejected_in_same_transaction(
    db_session: Session, person
) -> None:
    key = f"same-txn-{uuid.uuid4()}"
    db_session.add(make_transaction(person, idempotency_key=key))
    db_session.add(make_transaction(person, idempotency_key=key))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_idempotency_key_is_not_nullable(db_session: Session, person) -> None:
    txn = Transaction(
        event_type=EventType.mama_devuelve,
        amount=Decimal("5.00"),
        description="no key",
        event_date=date(2026, 8, 3),
        created_by=person,
    )
    db_session.add(txn)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_key_rejected_across_independent_committed_transactions(
    engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    """Second, fully separate transaction cannot reuse a committed key."""
    key = f"cross-txn-{uuid.uuid4()}"
    person_id: uuid.UUID | None = None
    try:
        # Transaction 1: commit a person + a transaction with `key`.
        s1 = session_factory()
        p = make_person()
        s1.add(p)
        s1.flush()
        person_id = p.id
        s1.add(make_transaction(p, idempotency_key=key))
        s1.commit()
        s1.close()

        # Transaction 2: a brand-new session/connection, same key -> rejected.
        s2 = session_factory()
        s2.add(make_transaction_by_id(person_id, key))
        with pytest.raises(IntegrityError):
            s2.commit()
        s2.close()
    finally:
        # DELETE on transaction is blocked by the append-only trigger (0002);
        # TRUNCATE does not fire row triggers.
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE transaction, person CASCADE"))


def make_transaction_by_id(person_id: uuid.UUID, key: str) -> Transaction:
    return Transaction(
        event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("35.50"),
        description="taxi",
        event_date=date(2026, 8, 30),
        created_by_id=person_id,
        idempotency_key=key,
    )
