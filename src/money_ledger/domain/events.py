"""The single source of truth for the financial sign of each event type.

PHASE-2.3 §5 / §9, PHASE-2.5 §12. Balance convention: S > 0 => Erick owes Mamá.

    mama_entrega_dinero   -> +amount
    erick_gasta_para_mama -> -amount
    erick_entrega_dinero  -> -amount
    mama_devuelve         -> -amount
    erick_devuelve        -> +amount

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
    EventType.mama_devuelve: -1,
    EventType.erick_devuelve: +1,
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
