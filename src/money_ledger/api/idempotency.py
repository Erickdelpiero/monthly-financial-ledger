"""Replay short-circuits, run BEFORE the text parser / LLM (PHASE-2.9 §6.3).

A repeated request that carries an ``idempotency_key`` must not re-invoke the
parser or the LLM fallback. These helpers decide, using only cheap fields,
whether the request is a replay (return the stored row), a genuine conflict
(raise), or new (return ``None`` -> parse and record normally).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from money_ledger.domain.errors import DuplicateIdempotencyKey
from money_ledger.models.enums import EventType
from money_ledger.models.transaction import Transaction
from money_ledger.services import find_by_idempotency_key


def transaction_replay(
    session: Session,
    *,
    idempotency_key: str,
    person_id: uuid.UUID,
    event_type: EventType,
    event_date: date,
) -> Optional[Transaction]:
    existing = find_by_idempotency_key(session, idempotency_key)
    if existing is None:
        return None
    if (
        existing.created_by_id == person_id
        and existing.event_type == event_type
        and existing.event_date == event_date
    ):
        return existing
    raise DuplicateIdempotencyKey(
        f"idempotency_key {idempotency_key!r} is already used by a different request"
    )


def correction_replay(
    session: Session, *, idempotency_key: str, target_id: uuid.UUID
) -> Optional[Transaction]:
    existing = find_by_idempotency_key(session, idempotency_key)
    if existing is None:
        return None
    predecessor = session.execute(
        select(Transaction.id).where(Transaction.superseded_by_id == existing.id)
    ).scalar_one_or_none()
    if predecessor == target_id:
        return existing
    raise DuplicateIdempotencyKey(
        f"idempotency_key {idempotency_key!r} is already used by a different correction"
    )
