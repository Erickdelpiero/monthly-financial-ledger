"""record_transaction service (PHASE-2.5 §8, §16; PHASE-2.6 §7)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from money_ledger.domain.errors import (
    DuplicateIdempotencyKey,
    InactivePerson,
    InvalidAmount,
    InvalidDescription,
    InvalidEventDate,
    InvalidEventType,
    InvalidIdempotencyKey,
    UnknownPerson,
)
from money_ledger.models.enums import EventType, TransactionStatus
from money_ledger.models.person import Person
from money_ledger.models.transaction import Transaction
from money_ledger.services import get_balance, record_transaction
from tests.conftest import make_person

TODAY = date(2026, 8, 31)


def _kwargs(person: Person, **overrides):
    base = dict(
        created_by_id=person.id,
        event_type=EventType.mama_entrega_dinero,
        amount=Decimal("100.00"),
        description="compras",
        event_date=date(2026, 8, 30),
        idempotency_key=f"rec-{uuid.uuid4()}",
        today=TODAY,
    )
    base.update(overrides)
    return base


def _count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Transaction)).scalar_one()


def test_happy_path_persists_active_row(db_session: Session, person: Person) -> None:
    row = record_transaction(db_session, **_kwargs(person))
    db_session.flush()

    assert isinstance(row.id, uuid.UUID)
    assert row.status is TransactionStatus.ACTIVE
    assert row.superseded_by_id is None
    fetched = db_session.get(Transaction, row.id)
    assert fetched is row
    assert get_balance(db_session).net == Decimal("100.00")


def test_amount_is_normalized_to_two_decimals(db_session: Session, person: Person) -> None:
    row = record_transaction(db_session, **_kwargs(person, amount=Decimal("100.5")))
    assert row.amount == Decimal("100.50")
    assert row.amount.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "bad_amount",
    [Decimal("0.00"), Decimal("-1.00"), Decimal("1.234"), Decimal("NaN"), Decimal("1E12")],
)
def test_invalid_amounts_are_rejected(db_session: Session, person: Person, bad_amount) -> None:
    with pytest.raises(InvalidAmount):
        record_transaction(db_session, **_kwargs(person, amount=bad_amount))
    assert _count(db_session) == 0


def test_float_amount_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(InvalidAmount):
        record_transaction(db_session, **_kwargs(person, amount=100.0))


def test_future_event_date_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(InvalidEventDate):
        record_transaction(db_session, **_kwargs(person, event_date=date(2026, 9, 1)))


def test_blank_description_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(InvalidDescription):
        record_transaction(db_session, **_kwargs(person, description="   "))


def test_blank_idempotency_key_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(InvalidIdempotencyKey):
        record_transaction(db_session, **_kwargs(person, idempotency_key=" "))


def test_unknown_event_type_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(InvalidEventType):
        record_transaction(db_session, **_kwargs(person, event_type="mama_regala"))


def test_unknown_person_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(UnknownPerson):
        record_transaction(db_session, **_kwargs(person, created_by_id=uuid.uuid4()))


def test_inactive_person_cannot_record(db_session: Session) -> None:
    inactive = make_person(name="inactive")
    inactive.is_active = False
    db_session.add(inactive)
    db_session.flush()
    with pytest.raises(InactivePerson):
        record_transaction(db_session, **_kwargs(inactive))


def test_same_key_same_payload_is_idempotent(db_session: Session, person: Person) -> None:
    kwargs = _kwargs(person, idempotency_key="rec-fixed")
    first = record_transaction(db_session, **kwargs)
    db_session.flush()
    second = record_transaction(db_session, **kwargs)

    assert second.id == first.id
    assert _count(db_session) == 1


def test_same_key_different_payload_conflicts(db_session: Session, person: Person) -> None:
    kwargs = _kwargs(person, idempotency_key="rec-conflict")
    record_transaction(db_session, **kwargs)
    db_session.flush()
    with pytest.raises(DuplicateIdempotencyKey):
        record_transaction(db_session, **{**kwargs, "amount": Decimal("999.00")})
    assert _count(db_session) == 1


def test_caller_transaction_survives_idempotency_conflict(
    db_session: Session, person: Person
) -> None:
    """After a DuplicateIdempotencyKey the session is still usable."""
    kwargs = _kwargs(person, idempotency_key="rec-survive")
    record_transaction(db_session, **kwargs)
    db_session.flush()
    with pytest.raises(DuplicateIdempotencyKey):
        record_transaction(db_session, **{**kwargs, "description": "otra cosa"})

    later = record_transaction(db_session, **_kwargs(person))
    db_session.flush()
    assert db_session.get(Transaction, later.id) is later
