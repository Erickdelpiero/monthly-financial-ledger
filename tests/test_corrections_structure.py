"""Structural support for corrections — NOT the correction-applying logic.

Block 1 only guarantees that the schema can *represent* a supersession chain
and that the database refuses incoherent rows. Actually performing a correction
(open a transaction, insert the new row, flip the old one to SUPERSEDED) is
Block 2 (PHASE-2.6 §9).

Model recap (PHASE-2.3 §11-13):
  * ACTIVE      -> superseded_by_id IS NULL, counts toward the balance
  * SUPERSEDED  -> superseded_by_id points at its replacement, kept for audit
  * chains A -> B -> C are allowed; only the tail (C) is ACTIVE
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from money_ledger.models import EventType, Transaction, TransactionStatus
from tests.conftest import make_transaction


def _row(person, *, status, superseded_by_id, key, row_id=None):
    return Transaction(
        id=row_id or uuid.uuid4(),
        event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("35.50"),
        description="taxi",
        event_date=date(2026, 8, 30),
        created_by=person,
        idempotency_key=key,
        status=status,
        superseded_by_id=superseded_by_id,
    )


def test_supersession_chain_can_be_represented(db_session: Session, person) -> None:
    c_id, b_id, a_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # Insert tail first, flushing each row, so every FK target already exists
    # (superseded_by_id is a plain column, not a relationship, so the unit of
    # work does not order these for us).
    for row_id, sup_id, key in [
        (c_id, None, "chain-c"),
        (b_id, c_id, "chain-b"),
        (a_id, b_id, "chain-a"),
    ]:
        status = (
            TransactionStatus.ACTIVE if sup_id is None else TransactionStatus.SUPERSEDED
        )
        db_session.add(
            _row(person, status=status, superseded_by_id=sup_id, key=key, row_id=row_id)
        )
        db_session.flush()

    active = (
        db_session.query(Transaction)
        .filter(Transaction.status == TransactionStatus.ACTIVE)
        .all()
    )
    assert [t.id for t in active] == [c_id]


def test_active_row_cannot_carry_a_superseded_by_pointer(db_session: Session, person) -> None:
    target = make_transaction(person, idempotency_key="incoherent-target")
    db_session.add(target)
    db_session.flush()

    db_session.add(
        _row(person, status=TransactionStatus.ACTIVE, superseded_by_id=target.id,
             key="incoherent-active")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_superseded_row_must_point_at_its_replacement(db_session: Session, person) -> None:
    db_session.add(
        _row(person, status=TransactionStatus.SUPERSEDED, superseded_by_id=None,
             key="incoherent-superseded")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_row_cannot_supersede_itself(db_session: Session, person) -> None:
    row_id = uuid.uuid4()
    db_session.add(
        _row(person, status=TransactionStatus.SUPERSEDED, superseded_by_id=row_id,
             key="self-supersede", row_id=row_id)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_superseded_by_foreign_key_is_enforced(db_session: Session, person) -> None:
    db_session.add(
        _row(person, status=TransactionStatus.SUPERSEDED, superseded_by_id=uuid.uuid4(),
             key="dangling-pointer")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_two_rows_cannot_share_one_superseded_by_target(
    db_session: Session, person
) -> None:
    """UNIQUE(superseded_by_id): a correction replaces exactly one prior row,
    so the chain cannot fork (A -> C and B -> C). (PHASE-2.5 §14.2)"""
    tail = make_transaction(person, idempotency_key="fork-tail")
    a = make_transaction(person, idempotency_key="fork-a")
    db_session.add_all([tail, a])
    db_session.flush()

    a.status = TransactionStatus.SUPERSEDED
    a.superseded_by_id = tail.id
    db_session.flush()

    db_session.add(
        _row(person, status=TransactionStatus.SUPERSEDED, superseded_by_id=tail.id,
             key="fork-b")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_default_row_has_null_superseded_by(db_session: Session, person) -> None:
    txn = make_transaction(person, idempotency_key="plain-active")
    db_session.add(txn)
    db_session.flush()
    db_session.refresh(txn)
    assert txn.superseded_by_id is None
    assert txn.status is TransactionStatus.ACTIVE


def test_transaction_has_self_referential_foreign_key(engine: Engine) -> None:
    fks = inspect(engine).get_foreign_keys("transaction")
    self_fks = [fk for fk in fks if fk["referred_table"] == "transaction"]
    assert len(self_fks) == 1
    assert self_fks[0]["constrained_columns"] == ["superseded_by_id"]
    assert self_fks[0]["referred_columns"] == ["id"]
