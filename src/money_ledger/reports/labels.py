"""Human-readable label for each ``event_type`` (PHASE-2.8 §5.2).

These are the strings the two users already see on the Telegram buttons
(``n8n/workflow-a-registro.json`` ``LABELS``); reusing them keeps the monthly
report worded the same way as the bot. PHASE-2.8 §4 leaves the exact wording to
implementation as long as the semantics hold.
"""

from __future__ import annotations

from money_ledger.models.enums import EventType

MOVEMENT_LABELS: dict[EventType, str] = {
    EventType.mama_entrega_dinero: "Mamá me entregó dinero",
    EventType.erick_gasta_para_mama: "Yo gasté para mamá",
    EventType.erick_entrega_dinero: "Yo le entregué dinero",
    EventType.mama_devuelve: "Mamá me devolvió dinero",
    EventType.erick_devuelve: "Yo le devolví dinero",
}

# Fail loudly at import if a new event type is ever added without a label.
assert set(MOVEMENT_LABELS) == set(EventType), "MOVEMENT_LABELS must cover every EventType"


def movement_label(event_type: EventType) -> str:
    return MOVEMENT_LABELS[event_type]
