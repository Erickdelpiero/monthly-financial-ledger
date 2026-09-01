"""Balance computation (PHASE-2.3 §3-4, §21; PHASE-2.5 §12-13). Pure, no DB."""

from __future__ import annotations

from decimal import Decimal

from money_ledger.domain.balance import Balance, Direction, compute_balance
from money_ledger.models.enums import EventType as E


def test_empty_ledger_is_no_debt() -> None:
    b = compute_balance([])
    assert isinstance(b, Balance)
    assert b.direction is Direction.NO_DEBT
    assert b.amount == Decimal("0.00")
    assert b.net == Decimal("0.00")
    assert b.currency == "PEN"


def test_single_incoming_event_means_erick_owes_mama() -> None:
    b = compute_balance([(E.mama_entrega_dinero, Decimal("100.00"))])
    assert b.direction is Direction.ERICK_OWES_MAMA
    assert b.amount == Decimal("100.00")
    assert b.net == Decimal("100.00")


def test_single_outgoing_event_means_mama_owes_erick() -> None:
    b = compute_balance([(E.erick_entrega_dinero, Decimal("40.00"))])
    assert b.direction is Direction.MAMA_OWES_ERICK
    assert b.amount == Decimal("40.00")
    assert b.net == Decimal("-40.00")


def test_events_can_net_exactly_to_zero() -> None:
    b = compute_balance(
        [
            (E.mama_entrega_dinero, Decimal("100.00")),
            (E.erick_gasta_para_mama, Decimal("70.00")),
            (E.erick_gasta_para_mama, Decimal("30.00")),
        ]
    )
    assert b.direction is Direction.NO_DEBT
    assert b.amount == Decimal("0.00")


def test_architecture_worked_example_section_21() -> None:
    # +100, -70, -40  =>  S = -10  =>  Mamá owes Erick 10.
    b = compute_balance(
        [
            (E.mama_entrega_dinero, Decimal("100.00")),
            (E.erick_gasta_para_mama, Decimal("70.00")),
            (E.erick_gasta_para_mama, Decimal("40.00")),
        ]
    )
    assert b.net == Decimal("-10.00")
    assert b.direction is Direction.MAMA_OWES_ERICK
    assert b.amount == Decimal("10.00")


def test_many_small_amounts_have_no_float_drift() -> None:
    rows = [(E.mama_entrega_dinero, Decimal("0.10"))] * 3
    assert compute_balance(rows).net == Decimal("0.30")


def test_returns_declared_two_decimal_scale() -> None:
    b = compute_balance([(E.mama_entrega_dinero, Decimal("5"))])
    assert b.net == Decimal("5.00")
    assert b.net.as_tuple().exponent == -2
