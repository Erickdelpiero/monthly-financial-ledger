"""Append-only guards from migration 0002 (F2).

Two triggers on `transaction`:
  * BEFORE DELETE -> always raises.
  * BEFORE UPDATE -> allows only the ACTIVE -> SUPERSEDED correction step
    (status + superseded_by_id, every other column unchanged, successor ACTIVE).

Uses committed rows because the point under test is direct-DML behaviour;
cleanup is TRUNCATE, which does not fire row triggers.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from money_ledger.models.enums import EventType
from money_ledger.models.transaction import Transaction
from money_ledger.services import apply_correction, record_transaction
from tests.conftest import make_person

TODAY = date(2026, 8, 31)


@pytest.fixture()
def committed(session_factory: sessionmaker[Session], engine: Engine):
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE transaction, person CASCADE"))


def _person(session: Session):
    p = make_person()
    session.add(p)
    session.flush()
    return p


def _active(session: Session, person, *, key: str | None = None) -> Transaction:
    row = record_transaction(
        session,
        created_by_id=person.id,
        event_type=EventType.mama_entrega_dinero,
        amount=Decimal("10.00"),
        description="seed",
        event_date=date(2026, 8, 30),
        idempotency_key=key or f"g-{uuid.uuid4()}",
        today=TODAY,
    )
    session.commit()
    return row


# --- trigger presence -------------------------------------------------------

@pytest.mark.parametrize(
    "trigger",
    ["trg_transaction_forbid_delete", "trg_transaction_guard_update"],
)
def test_trigger_is_installed(engine: Engine, trigger: str) -> None:
    with engine.connect() as conn:
        name = conn.execute(
            text(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgname = :t AND NOT tgisinternal"
            ),
            {"t": trigger},
        ).scalar()
    assert name == trigger


# --- DELETE ---------------------------------------------------------------

def test_raw_delete_is_blocked(committed: Session) -> None:
    row = _active(committed, _person(committed))
    with pytest.raises(IntegrityError):
        committed.execute(text("DELETE FROM transaction WHERE id = :i"), {"i": row.id})
        committed.commit()
    committed.rollback()
    assert committed.execute(text("SELECT count(*) FROM transaction")).scalar() == 1


def test_orm_delete_is_blocked(committed: Session) -> None:
    row = _active(committed, _person(committed))
    committed.delete(row)
    with pytest.raises(IntegrityError):
        committed.flush()
    committed.rollback()
    assert committed.get(Transaction, row.id) is not None


# --- UPDATE ---------------------------------------------------------------

def test_cannot_mutate_an_immutable_column(committed: Session) -> None:
    row = _active(committed, _person(committed))
    with pytest.raises(IntegrityError):
        committed.execute(
            text("UPDATE transaction SET amount = amount + 1 WHERE id = :i"),
            {"i": row.id},
        )
        committed.commit()
    committed.rollback()
    assert committed.execute(
        text("SELECT amount FROM transaction WHERE id = :i"), {"i": row.id}
    ).scalar() == Decimal("10.00")


def test_cannot_unsupersede_a_row(committed: Session) -> None:
    person = _person(committed)
    a = _active(committed, person)
    apply_correction(committed, target_id=a.id, created_by_id=person.id,
                     idempotency_key="unsup", amount=Decimal("12.00"), today=TODAY)
    committed.commit()

    with pytest.raises(IntegrityError):
        committed.execute(
            text(
                "UPDATE transaction "
                "SET status = 'ACTIVE', superseded_by_id = NULL WHERE id = :i"
            ),
            {"i": a.id},
        )
        committed.commit()
    committed.rollback()
    assert committed.execute(
        text("SELECT count(*) FROM transaction WHERE status = 'ACTIVE'")
    ).scalar() == 1


def test_cannot_supersede_into_a_non_active_successor(committed: Session) -> None:
    """Closing a cycle would point an ACTIVE row at an already-SUPERSEDED row."""
    person = _person(committed)
    a = _active(committed, person)
    b = apply_correction(committed, target_id=a.id, created_by_id=person.id,
                         idempotency_key="cyc", amount=Decimal("12.00"), today=TODAY)
    committed.commit()
    # a is SUPERSEDED, b is ACTIVE. Try to point b back at a.
    with pytest.raises(IntegrityError):
        committed.execute(
            text(
                "UPDATE transaction "
                "SET status = 'SUPERSEDED', superseded_by_id = :a WHERE id = :b"
            ),
            {"a": a.id, "b": b.id},
        )
        committed.commit()
    committed.rollback()


def test_legit_active_to_superseded_transition_is_allowed(committed: Session) -> None:
    person = _person(committed)
    a = _active(committed, person, key="legit-a")
    b = _active(committed, person, key="legit-b")  # a second ACTIVE row to point at
    committed.execute(
        text(
            "UPDATE transaction "
            "SET status = 'SUPERSEDED', superseded_by_id = :b WHERE id = :a"
        ),
        {"a": a.id, "b": b.id},
    )
    committed.commit()
    assert committed.execute(
        text("SELECT status FROM transaction WHERE id = :a"), {"a": a.id}
    ).scalar() == "SUPERSEDED"
