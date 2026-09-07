"""The single source of truth for the financial sign of each event type.

PHASE-2.3 §5 / §9, PHASE-2.5 §12. Balance convention: S > 0 => Erick owes Mamá.

    mama_entrega_dinero   -> +amount
    erick_gasta_para_mama -> -amount
    erick_entrega_dinero  -> -amount
    mama_devuelve         -> +amount
    erick_devuelve        -> -amount

The sign is set by *which direction the money physically moves*, not by whether
the movement is a fresh outlay or the repayment of an existing debt:

    Mamá -> Erick  (mama_entrega_dinero, mama_devuelve)   => S increases  (+)
    Erick -> Mamá  (erick_gasta_para_mama, erick_entrega_dinero,
                    erick_devuelve)                        => S decreases  (-)

So ``*_devuelve`` carries the *same* sign as the matching ``*_entrega`` event:
"Mamá me devolvió S/17" when Mamá owed Erick S/17 must bring S to 0, not deepen
the debt. The two labels are kept apart only for the ledger narrative / reports.

    !! This corrects an inverted sign in PHASE-2.3 §5 / §9 and PHASE-2.5 §12,
    !! found in the Block 6 E2E test: a `mama_devuelve` for the exact debt
    !! doubled it instead of settling it. See docs/decisions/block-1-followups.md.

The sign is never chosen by the user, n8n, or the LLM, and never stored on the
row -- the balance is always derived (PHASE-2.3 §26 P2).
"""

from __future__ import annotations

from decimal import Decimal

from money_ledger.domain.errors import InvalidEventType
from money_ledger.models.enums import EventType

SIGN: dict[EventType, int] = {
    EventType.mama_entrega_dinero: +1,
    EventType.erick_gasta_para_mama: -1,
    EventType.erick_entrega_dinero: -1,
    EventType.mama_devuelve: +1,
    EventType.erick_devuelve: -1,
}

# Fail loudly at import time if a new enum member is ever added without a sign.
assert set(SIGN) == set(EventType), "SIGN must map every EventType"


def parse_event_type(value: EventType | str) -> EventType:
    """Coerce an incoming value to a known ``EventType`` or raise."""
    if isinstance(value, EventType):
        return value
    try:
        return EventType(value)
    except ValueError as exc:
        raise InvalidEventType(f"unknown event_type: {value!r}") from exc


def signed_effect(event_type: EventType | str, amount: Decimal) -> Decimal:
    """Signed contribution of one event to the balance S (a Decimal)."""
    return SIGN[parse_event_type(event_type)] * amount
