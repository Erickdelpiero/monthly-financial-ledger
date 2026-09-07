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


# --- Repayments settle debts; they never deepen them (Block 6 E2E regression) ---
# PHASE-2.3 §5 / PHASE-2.5 §12 originally gave `mama_devuelve`/`erick_devuelve`
# the sign *opposite* to the matching `*_entrega` event. That doubled a debt when
# a person repaid it. These tests pin the corrected behaviour by outcome, not by
# a sign table, so the fix is protected for life. See block-1-followups.md.


def test_mama_devuelve_settles_the_exact_debt_to_zero() -> None:
    # The exact production sequence: Erick spent S/10 + S/7 for Mamá (the S/7 is
    # the ACTIVE row after correcting a S/5 entry), so Mamá owed Erick S/17.
    # Mamá then returns S/17 -> the debt is cleared, not doubled.
    b = compute_balance(
        [
            (E.erick_gasta_para_mama, Decimal("10.00")),
            (E.erick_gasta_para_mama, Decimal("7.00")),
            (E.mama_devuelve, Decimal("17.00")),
        ]
    )
    assert b.net == Decimal("0.00")
    assert b.direction is Direction.NO_DEBT
    assert b.amount == Decimal("0.00")


def test_erick_devuelve_settles_the_exact_debt_to_zero() -> None:
    # Mamá handed Erick S/50; Erick repays S/50 -> no debt.
    b = compute_balance(
        [
            (E.mama_entrega_dinero, Decimal("50.00")),
            (E.erick_devuelve, Decimal("50.00")),
        ]
    )
    assert b.net == Decimal("0.00")
    assert b.direction is Direction.NO_DEBT


def test_mama_devuelve_alone_moves_the_balance_toward_erick_being_owed_back() -> None:
    # A standalone `mama_devuelve` (Mamá overpays / prepays) must push S positive,
    # exactly like `mama_entrega_dinero` -- never negative.
    b = compute_balance([(E.mama_devuelve, Decimal("17.00"))])
    assert b.net == Decimal("17.00")
    assert b.direction is Direction.ERICK_OWES_MAMA


def test_erick_devuelve_alone_moves_the_balance_toward_mama_being_owed_back() -> None:
    b = compute_balance([(E.erick_devuelve, Decimal("17.00"))])
    assert b.net == Decimal("-17.00")
    assert b.direction is Direction.MAMA_OWES_ERICK


def test_partial_repayment_leaves_the_remaining_debt() -> None:
    # Mamá owed Erick S/17 and repays S/10 -> Mamá still owes S/7.
    b = compute_balance(
        [
            (E.erick_gasta_para_mama, Decimal("17.00")),
            (E.mama_devuelve, Decimal("10.00")),
        ]
    )
    assert b.net == Decimal("-7.00")
    assert b.direction is Direction.MAMA_OWES_ERICK
    assert b.amount == Decimal("7.00")
