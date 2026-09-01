"""JSON shapes for responses. Amounts are decimal strings (PHASE-2.5 §10/§13)."""

from __future__ import annotations

from typing import Optional

from money_ledger.domain.balance import Balance
from money_ledger.models.transaction import Transaction
from money_ledger.parsing.result import ParseSource


def balance_payload(balance: Balance) -> dict:
    return {
        "balance": str(balance.amount),
        "currency": balance.currency,
        "direction": balance.direction.value,
    }


def transaction_payload(
    txn: Transaction, *, parse_source: Optional[ParseSource] = None
) -> dict:
    payload = {
        "id": str(txn.id),
        "event_type": txn.event_type.value,
        "amount": str(txn.amount),
        "description": txn.description,
        "event_date": txn.event_date.isoformat(),
        "recorded_at": txn.recorded_at.isoformat(),
        "status": txn.status.value,
        "created_by": str(txn.created_by_id),
        "superseded_by": str(txn.superseded_by_id) if txn.superseded_by_id else None,
    }
    if parse_source is not None:
        payload["parse_source"] = parse_source.value
    return payload
