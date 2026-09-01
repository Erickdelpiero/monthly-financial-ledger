"""Structural integrity of Person and Transaction (PHASE-2.6 §13, PHASE-2.9 §4, §12)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from money_ledger.models import EventType, Person, Transaction, TransactionStatus
from tests.conftest import make_person, make_transaction


def test_person_insert_and_defaults(db_session: Session) -> None:
    p = make_person(name="Alice")
    db_session.add(p)
    db_session.flush()
    db_session.refresh(p)

    assert isinstance(p.id, uuid.UUID)
    assert p.is_active is True
    assert isinstance(p.created_at, datetime)


def test_transaction_insert_and_defaults(db_session: Session, person: Person) -> None:
    txn = make_transaction(person, amount=Decimal("35.50"))
    db_session.add(txn)
    db_session.flush()
    db_session.refresh(txn)

    assert isinstance(txn.id, uuid.UUID)
    assert txn.status is TransactionStatus.ACTIVE
    assert txn.superseded_by_id is None
    assert isinstance(txn.recorded_at, datetime)
    assert isinstance(txn.created_at, datetime)
    assert txn.event_date == date(2026, 8, 30)


@pytest.mark.parametrize("bad_amount", [Decimal("0.00"), Decimal("-0.01"), Decimal("-100.00")])
def test_amount_must_be_positive(db_session: Session, person: Person, bad_amount: Decimal) -> None:
    db_session.add(make_transaction(person, amount=bad_amount))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_amount_is_exact_decimal_with_cents(db_session: Session, person: Person) -> None:
    txn = make_transaction(person, amount=Decimal("100.00"))
    db_session.add(txn)
    db_session.flush()
    db_session.expire(txn)

    assert isinstance(txn.amount, Decimal)
    assert txn.amount == Decimal("100.00")


def test_amount_with_more_than_two_decimals_is_rounded_by_the_column(
    db_session: Session, person: Person
) -> None:
    """KNOWN BEHAVIOUR: NUMERIC(12,2) rounds to the cent on store. Rejecting
    amounts that are not representable in cents is a Python pre-insert
    validation in Block 2 (PHASE-2.3 §18), not a database constraint.
    See docs/decisions/block-1-followups.md.
    """
    txn = make_transaction(person, amount=Decimal("35.999"), idempotency_key="round-1")
    db_session.add(txn)
    db_session.flush()
    db_session.expire(txn)
    assert txn.amount == Decimal("36.00")


def test_sub_cent_amount_is_rounded_then_rejected_by_amount_positive(
    db_session: Session, person: Person
) -> None:
    # 0.004 -> rounded to 0.00 -> fails the amount > 0 check.
    db_session.add(
        make_transaction(person, amount=Decimal("0.004"), idempotency_key="round-2")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_amount_accumulation_has_no_float_error(db_session: Session, person: Person) -> None:
    # The classic 0.1 + 0.2 case must stay exact through the database.
    for i, cents in enumerate(["0.10", "0.20"]):
        db_session.add(
            make_transaction(person, amount=Decimal(cents), idempotency_key=f"acc-{i}")
        )
    db_session.flush()

    total = sum(
        (t.amount for t in db_session.query(Transaction).all()),
        start=Decimal("0.00"),
    )
    assert total == Decimal("0.30")


def test_description_must_not_be_blank(db_session: Session, person: Person) -> None:
    db_session.add(make_transaction(person, description="   "))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_person_name_must_not_be_blank(db_session: Session) -> None:
    db_session.add(make_person(name=""))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_event_type_enum_is_closed(db_session: Session) -> None:
    # Every declared value is accepted...
    for value in [e.value for e in EventType]:
        assert db_session.execute(
            text("SELECT CAST(:v AS event_type)"), {"v": value}
        ).scalar() == value

    # ...and anything else is rejected by the database itself.
    with pytest.raises(DataError):
        db_session.execute(text("SELECT 'not_a_real_type'::event_type"))


def test_created_by_foreign_key_is_enforced(db_session: Session) -> None:
    orphan = Transaction(
        event_type=EventType.mama_entrega_dinero,
        amount=Decimal("10.00"),
        description="orphan",
        event_date=date(2026, 8, 1),
        created_by_id=uuid.uuid4(),  # no such person
        idempotency_key=f"orphan-{uuid.uuid4()}",
    )
    db_session.add(orphan)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_telegram_user_id_is_unique(db_session: Session) -> None:
    db_session.add(make_person(telegram_user_id="dup-123"))
    db_session.add(make_person(telegram_user_id="dup-123"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_status_defaults_to_active_via_server_default(db_session: Session, person: Person) -> None:
    # Insert without specifying status at all; the DB server default fills it.
    db_session.execute(
        text(
            "INSERT INTO transaction "
            "(id, event_type, amount, description, event_date, created_by_id, idempotency_key) "
            "VALUES (:id, 'erick_devuelve', 12.00, 'x', :d, :cby, :key)"
        ),
        {
            "id": uuid.uuid4(),
            "d": date(2026, 8, 2),
            "cby": person.id,
            "key": f"srvdef-{uuid.uuid4()}",
        },
    )
    status = db_session.execute(
        text("SELECT status FROM transaction WHERE idempotency_key LIKE 'srvdef-%'")
    ).scalar()
    assert status == "ACTIVE"
