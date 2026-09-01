"""Balance computation (PHASE-2.3 §3-4, PHASE-2.5 §12-13).

    S = Sum( signed_effect(event) for event in ACTIVE transactions )

The balance is always derived from the ledger; it is never stored or edited
(PHASE-2.3 §26 P2). ``compute_balance`` is a pure function over ``(event_type,
amount)`` pairs so it can be unit-tested without a database; the service layer
supplies the ACTIVE rows.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from money_ledger.domain.events import signed_effect
from money_ledger.domain.money import CURRENCY
from money_ledger.models.enums import EventType

_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")


class Direction(str, enum.Enum):
    """PHASE-2.5 §13. S = 0 maps to NO_DEBT here; if the API must emit ``null``
    for that case (cf. PHASE-2.9 §4.2) it projects this value at the edge."""

    ERICK_OWES_MAMA = "erick_owes_mama"
    MAMA_OWES_ERICK = "mama_owes_erick"
    NO_DEBT = "no_debt"


@dataclass(frozen=True)
class Balance:
    amount: Decimal      # non-negative magnitude of the net debt
    currency: str        # always "PEN" in v1
    direction: Direction
    net: Decimal         # signed S (audit/debug); positive => Erick owes Mamá


def direction_for(net: Decimal) -> Direction:
    if net > 0:
        return Direction.ERICK_OWES_MAMA
    if net < 0:
        return Direction.MAMA_OWES_ERICK
    return Direction.NO_DEBT


def compute_balance(rows: Iterable[tuple[EventType, Decimal]]) -> Balance:
    net = sum((signed_effect(event_type, amount) for event_type, amount in rows), _ZERO)
    net = net.quantize(_CENT)
    return Balance(
        amount=abs(net),
        currency=CURRENCY,
        direction=direction_for(net),
        net=net,
    )
