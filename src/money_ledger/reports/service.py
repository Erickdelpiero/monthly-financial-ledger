"""Weekly and monthly report content, derived from the ledger.

* The weekly report is text only (PHASE-2.8 §4): current bilateral balance and
  who owes whom.
* The monthly report is an executive summary (the same current balance,
  PHASE-2.8 §5.1) plus the detailed transaction table for that calendar month
  (PHASE-2.8 §5.2).

v1 minimum (Erick, Block 7 scope): the monthly table lists only the currently
ACTIVE version of each row. A correction is reflected because only its ACTIVE
result is shown; superseded rows and correction markers are not displayed.

The month filter is on ``event_date`` (when the movement happened), not on the
registration timestamp -- the monthly report audits a period of real events,
so a movement registered late still lands in the month it occurred.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from money_ledger.domain.balance import Balance, Direction
from money_ledger.domain.errors import ValidationError
from money_ledger.models.enums import EventType, TransactionStatus
from money_ledger.models.transaction import Transaction
from money_ledger.reports.labels import movement_label
from money_ledger.services import get_balance

_MIN_YEAR, _MAX_YEAR = 2000, 2100

_MONTHS_ES = (
    "",
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def fmt_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def debt_line(balance: Balance) -> str:
    """"Erick debe a Mamá: S/ 12.50" / "Mamá debe a Erick: S/ 8.00" /
    "No hay deuda pendiente." (PHASE-2.8 §4)."""
    if balance.direction is Direction.ERICK_OWES_MAMA:
        return f"Erick debe a Mamá: S/ {fmt_amount(balance.amount)}"
    if balance.direction is Direction.MAMA_OWES_ERICK:
        return f"Mamá debe a Erick: S/ {fmt_amount(balance.amount)}"
    return "No hay deuda pendiente."


def weekly_text(balance: Balance) -> str:
    """The fixed weekly template (PHASE-2.8 §4)."""
    body = (
        "No hay deuda pendiente.\nSaldo: S/ 0.00"
        if balance.direction is Direction.NO_DEBT
        else debt_line(balance)
    )
    return f"📊 Saldo actual\n\n{body}"


def month_name_es(month: int) -> str:
    return _MONTHS_ES[month]


@dataclass(frozen=True)
class WeeklyReport:
    balance: Balance
    text: str


@dataclass(frozen=True)
class MonthlyRow:
    event_date: date
    recorded_at: datetime          # timezone-aware, as stored
    person_name: str
    event_type: EventType
    movement_label: str
    amount: Decimal
    description: str


@dataclass(frozen=True)
class MonthlyReport:
    year: int
    month: int
    balance: Balance               # current bilateral balance (global, not month-scoped)
    rows: tuple[MonthlyRow, ...]

    @property
    def period_label(self) -> str:
        return f"{month_name_es(self.month)} {self.year}"


def weekly_report(session: Session) -> WeeklyReport:
    balance = get_balance(session)
    return WeeklyReport(balance=balance, text=weekly_text(balance))


def _validate_period(year: int, month: int) -> None:
    if not (1 <= month <= 12) or not (_MIN_YEAR <= year <= _MAX_YEAR):
        raise ValidationError(
            f"report period out of range: year must be {_MIN_YEAR}-{_MAX_YEAR}, "
            "month 1-12"
        )


def monthly_report(session: Session, *, year: int, month: int) -> MonthlyReport:
    _validate_period(year, month)
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    stmt = (
        select(Transaction)
        .options(joinedload(Transaction.created_by))
        .where(
            Transaction.status == TransactionStatus.ACTIVE,
            Transaction.event_date >= first,
            Transaction.event_date <= last,
        )
        .order_by(Transaction.event_date, Transaction.recorded_at, Transaction.id)
    )
    rows = tuple(
        MonthlyRow(
            event_date=txn.event_date,
            recorded_at=txn.recorded_at,
            person_name=txn.created_by.name,
            event_type=txn.event_type,
            movement_label=movement_label(txn.event_type),
            amount=txn.amount,
            description=txn.description,
        )
        for txn in session.execute(stmt).scalars()
    )
    return MonthlyReport(
        year=year, month=month, balance=get_balance(session), rows=rows
    )
