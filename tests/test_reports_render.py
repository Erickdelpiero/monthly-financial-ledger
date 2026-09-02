"""render_monthly_png (PHASE-2.8 §5-6). Pure: builds a report by hand.

The visual design is implementation-defined (PHASE-2.8 §16); these tests only
assert we emit real, non-trivial PNG bytes for both the empty and populated
cases -- they do not compare pixels.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from money_ledger.domain.balance import Balance, Direction
from money_ledger.models.enums import EventType
from money_ledger.reports.render import render_monthly_png
from money_ledger.reports.service import MonthlyReport, MonthlyRow

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _balance(net: str) -> Balance:
    n = Decimal(net)
    direction = (
        Direction.NO_DEBT
        if n == 0
        else Direction.ERICK_OWES_MAMA
        if n > 0
        else Direction.MAMA_OWES_ERICK
    )
    return Balance(amount=abs(n), currency="PEN", direction=direction, net=n)


def _row(**kw) -> MonthlyRow:
    base = dict(
        event_date=date(2026, 8, 10),
        recorded_at=datetime(2026, 8, 10, 15, 30, tzinfo=timezone.utc),
        person_name="Erick",
        event_type=EventType.erick_gasta_para_mama,
        movement_label="Yo gasté para mamá",
        amount=Decimal("70.00"),
        description="Supermercado",
    )
    base.update(kw)
    return MonthlyRow(**base)


def test_empty_month_is_valid_png() -> None:
    report = MonthlyReport(year=2026, month=8, balance=_balance("0.00"), rows=())
    png = render_monthly_png(report)
    assert png.startswith(_PNG_MAGIC)
    assert len(png) > 1000


def test_populated_month_is_valid_png() -> None:
    rows = tuple(
        _row(
            event_date=date(2026, 8, d),
            description=f"movimiento {d} con una descripción larga para el layout",
            amount=Decimal(f"{d}.50"),
        )
        for d in (3, 8, 14, 20)
    )
    report = MonthlyReport(year=2026, month=8, balance=_balance("125.50"), rows=rows)
    png = render_monthly_png(report)
    assert png.startswith(_PNG_MAGIC)
    assert len(png) > 1000


def test_naive_recorded_at_is_tolerated() -> None:
    report = MonthlyReport(
        year=2026,
        month=8,
        balance=_balance("-8.00"),
        rows=(_row(recorded_at=datetime(2026, 8, 10, 15, 30)),),  # no tzinfo
    )
    assert render_monthly_png(report).startswith(_PNG_MAGIC)
