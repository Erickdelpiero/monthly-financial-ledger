"""weekly_report / monthly_report content (PHASE-2.8 §4-5, Block 7).

v1 minimum: the monthly table shows only the ACTIVE version of each row, filtered
by ``event_date`` month; the executive balance is the current global bilateral
balance, not a month-scoped figure.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from money_ledger.domain.balance import Direction
from money_ledger.domain.errors import ValidationError
from money_ledger.models.enums import EventType
from money_ledger.models.person import Person
from money_ledger.models.transaction import Transaction
from money_ledger.reports import monthly_report, weekly_report
from money_ledger.services import apply_correction, record_transaction
from tests.conftest import make_person

FAR_FUTURE = date(2027, 12, 31)  # lets the services accept 2026 event dates


def _person(db_session: Session, name: str) -> Person:
    p = make_person(name=name, telegram_user_id=f"tg-{uuid.uuid4()}")
    db_session.add(p)
    db_session.flush()
    return p


def _tx(
    db_session: Session,
    person: Person,
    *,
    event_type: EventType = EventType.erick_gasta_para_mama,
    amount: str = "10.00",
    description: str = "x",
    event_date: date = date(2026, 8, 10),
    recorded_at: datetime | None = None,
) -> Transaction:
    row = Transaction(
        created_by_id=person.id,
        event_type=event_type,
        amount=Decimal(amount),
        description=description,
        event_date=event_date,
        idempotency_key=f"seed-{uuid.uuid4()}",
    )
    if recorded_at is not None:
        row.recorded_at = recorded_at
    db_session.add(row)
    db_session.flush()
    return row


# --- weekly -------------------------------------------------------------------

def test_weekly_no_debt(db_session: Session) -> None:
    r = weekly_report(db_session)
    assert r.balance.direction is Direction.NO_DEBT
    assert r.text == "📊 Saldo actual\n\nNo hay deuda pendiente.\nSaldo: S/ 0.00"


def test_weekly_erick_owes_mama(db_session: Session, person: Person) -> None:
    _tx(db_session, person, event_type=EventType.mama_entrega_dinero, amount="100.00")
    r = weekly_report(db_session)
    assert r.balance.direction is Direction.ERICK_OWES_MAMA
    assert r.text == "📊 Saldo actual\n\nErick debe a Mamá: S/ 100.00"


def test_weekly_mama_owes_erick(db_session: Session, person: Person) -> None:
    _tx(db_session, person, event_type=EventType.erick_entrega_dinero, amount="40.00")
    r = weekly_report(db_session)
    assert r.balance.direction is Direction.MAMA_OWES_ERICK
    assert r.text == "📊 Saldo actual\n\nMamá debe a Erick: S/ 40.00"


# --- monthly ----------------------------------------------------------------

def test_monthly_filters_by_event_date_month(db_session: Session, person: Person) -> None:
    _tx(db_session, person, description="julio", event_date=date(2026, 7, 31))
    _tx(db_session, person, description="agosto-1", event_date=date(2026, 8, 1))
    _tx(db_session, person, description="agosto-31", event_date=date(2026, 8, 31))
    _tx(db_session, person, description="septiembre", event_date=date(2026, 9, 1))

    report = monthly_report(db_session, year=2026, month=8)
    assert [row.description for row in report.rows] == ["agosto-1", "agosto-31"]


def test_monthly_rows_are_chronological(db_session: Session, person: Person) -> None:
    _tx(db_session, person, description="d20", event_date=date(2026, 8, 20))
    _tx(db_session, person, description="d10", event_date=date(2026, 8, 10))
    _tx(db_session, person, description="d15", event_date=date(2026, 8, 15))
    report = monthly_report(db_session, year=2026, month=8)
    assert [row.description for row in report.rows] == ["d10", "d15", "d20"]


def test_monthly_shows_only_the_active_version(db_session: Session, person: Person) -> None:
    original = record_transaction(
        db_session,
        created_by_id=person.id,
        event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("10.00"),
        description="original",
        event_date=date(2026, 8, 12),
        idempotency_key=f"orig-{uuid.uuid4()}",
        today=FAR_FUTURE,
    )
    db_session.flush()
    apply_correction(
        db_session,
        target_id=original.id,
        created_by_id=person.id,
        idempotency_key=f"corr-{uuid.uuid4()}",
        amount=Decimal("12.00"),
        description="corregido",
        today=FAR_FUTURE,
    )
    db_session.flush()

    report = monthly_report(db_session, year=2026, month=8)
    assert len(report.rows) == 1
    assert report.rows[0].description == "corregido"
    assert report.rows[0].amount == Decimal("12.00")


def test_correction_moves_a_row_to_its_new_month(
    db_session: Session, person: Person
) -> None:
    original = record_transaction(
        db_session,
        created_by_id=person.id,
        event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("25.00"),
        description="mudanza",
        event_date=date(2026, 8, 15),
        idempotency_key=f"orig-{uuid.uuid4()}",
        today=FAR_FUTURE,
    )
    db_session.flush()

    assert [r.description for r in monthly_report(db_session, year=2026, month=8).rows] == ["mudanza"]
    assert monthly_report(db_session, year=2026, month=9).rows == ()

    apply_correction(
        db_session,
        target_id=original.id,
        created_by_id=person.id,
        idempotency_key=f"corr-{uuid.uuid4()}",
        event_date=date(2026, 9, 15),
        today=FAR_FUTURE,
    )
    db_session.flush()

    # The ACTIVE row now carries the September date: it leaves August and
    # appears in September (same ACTIVE + event_date filter, B7-4).
    assert monthly_report(db_session, year=2026, month=8).rows == ()
    sept = monthly_report(db_session, year=2026, month=9).rows
    assert [(r.description, r.event_date, r.amount) for r in sept] == [
        ("mudanza", date(2026, 9, 15), Decimal("25.00"))
    ]


def test_monthly_row_fields(db_session: Session) -> None:
    erick = _person(db_session, "Erick")
    _tx(
        db_session,
        erick,
        event_type=EventType.erick_gasta_para_mama,
        amount="70.00",
        description="Supermercado",
        event_date=date(2026, 8, 5),
        recorded_at=datetime(2026, 8, 5, 13, 14, tzinfo=timezone.utc),
    )
    row = monthly_report(db_session, year=2026, month=8).rows[0]
    assert row.person_name == "Erick"
    assert row.movement_label == "Yo gasté para mamá"
    assert row.event_type is EventType.erick_gasta_para_mama
    assert row.amount == Decimal("70.00")
    assert row.description == "Supermercado"
    assert row.event_date == date(2026, 8, 5)


def test_monthly_balance_is_global_not_month_scoped(
    db_session: Session, person: Person
) -> None:
    _tx(db_session, person, event_type=EventType.mama_entrega_dinero, amount="100.00",
        event_date=date(2026, 7, 15))
    _tx(db_session, person, event_type=EventType.erick_entrega_dinero, amount="30.00",
        event_date=date(2026, 8, 15))

    report = monthly_report(db_session, year=2026, month=8)
    assert [row.description for row in report.rows] == ["x"]  # only the August row
    assert report.balance.direction is Direction.ERICK_OWES_MAMA
    assert report.balance.amount == Decimal("70.00")  # 100 (Jul) - 30 (Aug)


def test_monthly_empty_month(db_session: Session, person: Person) -> None:
    _tx(db_session, person, event_date=date(2026, 8, 10))
    report = monthly_report(db_session, year=2026, month=3)
    assert report.rows == ()
    assert report.period_label == "Marzo 2026"
    assert report.balance.direction is Direction.MAMA_OWES_ERICK  # the Aug row still counts


@pytest.mark.parametrize("year,month", [(2026, 0), (2026, 13), (1999, 6), (2101, 6)])
def test_monthly_invalid_period_raises(db_session: Session, year: int, month: int) -> None:
    with pytest.raises(ValidationError):
        monthly_report(db_session, year=year, month=month)
