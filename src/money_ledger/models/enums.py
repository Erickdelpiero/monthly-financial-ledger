"""Closed enumerations for the ledger.

These are stored as native PostgreSQL ENUM types. The database rejects any
value outside these sets — an LLM or n8n cannot introduce a new event type
(architecture PHASE-2.3 §5, PHASE-2.5 §8.3).
"""

from __future__ import annotations

import enum


class EventType(str, enum.Enum):
    """The five v1 event types. Concrete naming, confirmed for implementation.

    The signed effect of each type on the balance S is defined in Block 2, not
    here. For reference only (PHASE-2.5 §12):
        mama_entrega_dinero   -> +amount
        erick_gasta_para_mama -> -amount
        erick_entrega_dinero  -> -amount
        mama_devuelve         -> -amount
        erick_devuelve        -> +amount
    """

    mama_entrega_dinero = "mama_entrega_dinero"
    erick_gasta_para_mama = "erick_gasta_para_mama"
    erick_entrega_dinero = "erick_entrega_dinero"
    mama_devuelve = "mama_devuelve"
    erick_devuelve = "erick_devuelve"


class TransactionStatus(str, enum.Enum):
    """Lifecycle state of a ledger row (PHASE-2.3 §11).

    ACTIVE      -> participates in the balance.
    SUPERSEDED  -> replaced by a correction; kept for audit, excluded from balance.
    """

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


# PostgreSQL type names (referenced by models and the initial migration).
EVENT_TYPE_ENUM_NAME = "event_type"
TRANSACTION_STATUS_ENUM_NAME = "transaction_status"
