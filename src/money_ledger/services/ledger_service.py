"""Ledger services: record a transaction, apply a correction, read the balance.

Design notes
------------
* These functions operate **within the caller's transaction**. They ``flush``
  but never ``commit`` -- the API layer (Block 4) or a test owns the commit.
* ``record_transaction`` and ``apply_correction`` wrap their writes in a
  SAVEPOINT (``session.begin_nested``) so a unique-key clash can be turned into
  a deterministic response without poisoning the caller's transaction
  (PHASE-2.5 §16, PHASE-2.6 §7 / §9).
* The sign of an event is never stored; ``get_balance`` derives S from the
  ACTIVE rows via :func:`money_ledger.domain.balance.compute_balance`.
* Identity: the caller passes an already-resolved ``created_by_id``. Resolving
  ``telegram_user_id -> person_id`` and rejecting unknown Telegram users is
  Block 4 (F3 in docs/decisions/block-1-followups.md).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from money_ledger.domain.balance import Balance, compute_balance
from money_ledger.domain.errors import (
    CorrectionNotAllowed,
    DuplicateIdempotencyKey,
    InactivePerson,
    InvalidDescription,
    InvalidEventDate,
    InvalidIdempotencyKey,
    TransactionNotActive,
    TransactionNotFound,
    UnknownPerson,
)
from money_ledger.domain.events import parse_event_type
from money_ledger.domain.money import normalize_amount
from money_ledger.models.enums import EventType, TransactionStatus
from money_ledger.models.person import Person
from money_ledger.models.transaction import Transaction

_LIMA = ZoneInfo("America/Lima")
_IDEMPOTENCY_CONSTRAINT = "uq_transaction_idempotency_key"


# --- validation helpers ---------------------------------------------------

def _today_lima() -> date:
    return datetime.now(tz=_LIMA).date()


def _clean_description(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDescription("description must not be blank")
    return value.strip()


def _check_event_date(value: date, *, today: Optional[date]) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise InvalidEventDate("event_date must be a calendar date")
    reference = today or _today_lima()
    if value > reference:
        raise InvalidEventDate("event_date cannot be in the future")
    return value


def _clean_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidIdempotencyKey("idempotency_key must not be blank")
    return value


def _load_active_person(session: Session, person_id: uuid.UUID) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise UnknownPerson(f"no person with id {person_id}")
    if not person.is_active:
        raise InactivePerson(f"person {person_id} is inactive")
    return person


def _is_unique_violation(exc: IntegrityError, constraint: Optional[str] = None) -> bool:
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) != "23505":
        return False
    if constraint is None:
        return True
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


def _row_by_idempotency_key(session: Session, key: str) -> Optional[Transaction]:
    return session.execute(
        select(Transaction).where(Transaction.idempotency_key == key)
    ).scalar_one_or_none()


def find_by_idempotency_key(session: Session, idempotency_key: str) -> Optional[Transaction]:
    """The row already stored for ``idempotency_key``, or ``None``.

    Lets callers short-circuit a repeated request before doing any expensive
    work such as parsing (PHASE-2.9 §6.3).
    """
    return _row_by_idempotency_key(session, idempotency_key)


# --- public API ---------------------------------------------------------

def record_transaction(
    session: Session,
    *,
    created_by_id: uuid.UUID,
    event_type: EventType | str,
    amount: Decimal,
    description: str,
    event_date: date,
    idempotency_key: str,
    today: Optional[date] = None,
) -> Transaction:
    """Persist a new ledger transaction.

    Idempotent on ``idempotency_key``: a repeated call with the same key and an
    identical payload returns the already-stored row; a repeated key with a
    different payload raises :class:`DuplicateIdempotencyKey`.
    """
    key = _clean_idempotency_key(idempotency_key)
    event = parse_event_type(event_type)
    money = normalize_amount(amount)
    text = _clean_description(description)
    day = _check_event_date(event_date, today=today)
    _load_active_person(session, created_by_id)

    row = Transaction(
        created_by_id=created_by_id,
        event_type=event,
        amount=money,
        description=text,
        event_date=day,
        idempotency_key=key,
    )
    try:
        # Add inside the SAVEPOINT and let its commit flush: an IntegrityError
        # raised by an *explicit* flush inside begin_nested() does not leave the
        # session recoverable, but one raised on the savepoint's own commit does.
        with session.begin_nested():
            session.add(row)
    except IntegrityError as exc:
        if not _is_unique_violation(exc, _IDEMPOTENCY_CONSTRAINT):
            raise
        if row in session:
            session.expunge(row)
        existing = _row_by_idempotency_key(session, key)
        if existing is not None and _same_payload(
            existing,
            created_by_id=created_by_id,
            event_type=event,
            amount=money,
            description=text,
            event_date=day,
        ):
            return existing
        raise DuplicateIdempotencyKey(
            f"idempotency_key {key!r} is already used by a different transaction"
        ) from exc
    return row


def apply_correction(
    session: Session,
    *,
    target_id: uuid.UUID,
    created_by_id: uuid.UUID,
    idempotency_key: str,
    event_type: EventType | str | None = None,
    amount: Decimal | None = None,
    description: str | None = None,
    event_date: date | None = None,
    today: Optional[date] = None,
) -> Transaction:
    """Replace the currently ACTIVE transaction ``target_id`` with a correction.

    Atomic (single SAVEPOINT): inserts the new ACTIVE row and flips the target
    to SUPERSEDED, or does neither. Only omitted fields are copied from the
    target; ``created_by_id`` is the person performing the correction (recorded
    on the new row -- it is not copied from the target). Correcting a non-ACTIVE
    row raises :class:`TransactionNotActive` (PHASE-2.5 §14.2, PHASE-2.6 §9/§12).

    Idempotent on ``idempotency_key``: a repeated call for the same target with
    an identical resolved payload returns the stored correction; a repeated key
    with a different payload or target raises :class:`DuplicateIdempotencyKey`.
    This holds for concurrent retries too -- the key is re-checked after the
    target row lock is taken and again on a unique-key conflict.
    """
    key = _clean_idempotency_key(idempotency_key)

    # Validate the supplied fields up front: a malformed request must raise a
    # validation error regardless of idempotency state.
    new_event_type = parse_event_type(event_type) if event_type is not None else None
    new_amount = normalize_amount(amount) if amount is not None else None
    new_description = _clean_description(description) if description is not None else None
    new_event_date = (
        _check_event_date(event_date, today=today) if event_date is not None else None
    )
    _load_active_person(session, created_by_id)

    def _resolved(base: Transaction) -> dict:
        return dict(
            created_by_id=created_by_id,
            event_type=new_event_type if new_event_type is not None else base.event_type,
            amount=new_amount if new_amount is not None else base.amount,
            description=(
                new_description if new_description is not None else base.description
            ),
            event_date=(
                new_event_date if new_event_date is not None else base.event_date
            ),
        )

    def _replay_or_conflict(existing: Transaction) -> Transaction:
        original = session.execute(
            select(Transaction).where(Transaction.superseded_by_id == existing.id)
        ).scalar_one_or_none()
        if (
            original is not None
            and original.id == target_id
            and _same_payload(existing, **_resolved(original))
        ):
            return existing
        raise DuplicateIdempotencyKey(
            f"idempotency_key {key!r} is already used by a different correction"
        )

    replay = _row_by_idempotency_key(session, key)
    if replay is not None:
        return _replay_or_conflict(replay)

    # Explicit SAVEPOINT: this block needs a mid-flush (to assign correction.id),
    # so it manages the savepoint by hand -- sp.rollback() recovers the session
    # after any failure, where a begin_nested() context manager would not.
    savepoint = session.begin_nested()
    try:
        target = session.get(Transaction, target_id, with_for_update=True)

        # Re-check now that the row lock is held: a concurrent request with the
        # same key may have committed while we waited on the lock.
        replay = _row_by_idempotency_key(session, key)
        if replay is not None:
            savepoint.rollback()
            return _replay_or_conflict(replay)

        if target is None:
            raise TransactionNotFound(f"no transaction with id {target_id}")
        if target.status is not TransactionStatus.ACTIVE:
            raise TransactionNotActive(
                f"transaction {target_id} is {target.status.value}; "
                "correct the currently active version instead"
            )
        if target.created_by_id != created_by_id:
            # v1 policy: each person corrects only their own entries
            # (PHASE-2.10 §18.1 / §29.9).
            raise CorrectionNotAllowed(
                f"transaction {target_id} was registered by someone else"
            )

        correction = Transaction(idempotency_key=key, **_resolved(target))
        session.add(correction)
        session.flush()  # assigns correction.id

        target.status = TransactionStatus.SUPERSEDED
        target.superseded_by_id = correction.id
        session.flush()
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        if _is_unique_violation(exc, _IDEMPOTENCY_CONSTRAINT):
            raced = _row_by_idempotency_key(session, key)
            if raced is not None:
                return _replay_or_conflict(raced)
            raise DuplicateIdempotencyKey(
                f"idempotency_key {key!r} is already used"
            ) from exc
        raise
    except BaseException:
        savepoint.rollback()
        raise
    return correction


def get_balance(session: Session) -> Balance:
    """Current bilateral balance, derived from ACTIVE transactions only."""
    rows = session.execute(
        select(Transaction.event_type, Transaction.amount).where(
            Transaction.status == TransactionStatus.ACTIVE
        )
    ).all()
    return compute_balance((event_type, amount) for event_type, amount in rows)


def list_recent_transactions(
    session: Session,
    *,
    created_by_id: uuid.UUID,
    status: Optional[TransactionStatus] = TransactionStatus.ACTIVE,
    limit: int = 5,
) -> list[Transaction]:
    """A person's most recent rows, newest event first.

    A read-only projection for the Telegram correction picker (PHASE-2.10 §18.1).
    ``status=None`` returns every status.
    """
    stmt = select(Transaction).where(Transaction.created_by_id == created_by_id)
    if status is not None:
        stmt = stmt.where(Transaction.status == status)
    stmt = stmt.order_by(
        Transaction.event_date.desc(),
        Transaction.recorded_at.desc(),
        Transaction.id.desc(),  # stable tiebreaker when timestamps collide
    ).limit(limit)
    return list(session.execute(stmt).scalars())


def _same_payload(
    row: Transaction,
    *,
    created_by_id: uuid.UUID,
    event_type: EventType,
    amount: Decimal,
    description: str,
    event_date: date,
) -> bool:
    return (
        row.created_by_id == created_by_id
        and row.event_type == event_type
        and row.amount == amount
        and row.description == description
        and row.event_date == event_date
    )
