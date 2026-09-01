"""Transaction entity — the append-only ledger row (PHASE-2.3 §7.2, PHASE-2.6).

Block 1 = structure only. This module intentionally does NOT contain:
  * the event_type -> signed effect mapping (Block 2),
  * balance calculation (Block 2),
  * the logic that applies a correction / flips ACTIVE -> SUPERSEDED (Block 2).

What it DOES provide is the schema plus the structural invariants the database
must enforce regardless of application code (PHASE-2.6 §13):
  * amount is a positive exact decimal (never float); the NUMERIC(12,2) column
    rounds to the cent on store -- rejecting amounts that are not representable
    in cents is a Python pre-insert validation in Block 2 (PHASE-2.3 §18),
  * event_type / status are closed enums,
  * idempotency_key is UNIQUE at the database level (PHASE-2.6 §7.1),
  * a row is either (ACTIVE, no superseded_by) or (SUPERSEDED, has superseded_by),
  * a row cannot supersede itself,
  * superseded_by_id is UNIQUE -> a correction replaces exactly one prior row,
    so the correction chain is linear and cannot fork (PHASE-2.5 §14.2).

Not enforced here (see docs/decisions/block-1-followups.md): cycle prevention
in the correction chain, and blocking direct UPDATE/DELETE of ledger rows --
both require Block 2's correction service and/or production role grants.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from money_ledger.db.base import Base
from money_ledger.models.enums import (
    EVENT_TYPE_ENUM_NAME,
    TRANSACTION_STATUS_ENUM_NAME,
    EventType,
    TransactionStatus,
)

if TYPE_CHECKING:
    from money_ledger.models.person import Person

# The initial Alembic migration owns the lifecycle of these PostgreSQL ENUM
# types, so the ORM must not try to CREATE/DROP them (create_type=False).
_event_type = PgEnum(
    EventType,
    name=EVENT_TYPE_ENUM_NAME,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_transaction_status = PgEnum(
    TransactionStatus,
    name=TRANSACTION_STATUS_ENUM_NAME,
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("length(btrim(description)) > 0", name="description_not_blank"),
        CheckConstraint(
            "length(btrim(idempotency_key)) > 0", name="idempotency_key_not_blank"
        ),
        CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name="no_self_supersede",
        ),
        CheckConstraint(
            "(status = 'ACTIVE'::transaction_status AND superseded_by_id IS NULL) "
            "OR (status = 'SUPERSEDED'::transaction_status AND superseded_by_id IS NOT NULL)",
            name="status_supersede_consistency",
        ),
        # A correction replaces exactly one prior row: UNIQUE prevents a forked
        # chain (A -> C and B -> C). Multiple ACTIVE rows keep superseded_by_id
        # NULL, and PostgreSQL treats NULLs as distinct, so this is not a
        # limit on the number of ACTIVE rows. Also backs FK lookups.
        UniqueConstraint("superseded_by_id", name="uq_transaction_superseded_by_id"),
        Index("ix_transaction_status", "status"),
        Index("ix_transaction_event_date", "event_date"),
        Index("ix_transaction_created_by_id", "created_by_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)

    event_type: Mapped[EventType] = mapped_column(_event_type, nullable=False)

    # Exact decimal money. Python side uses Decimal; PostgreSQL uses NUMERIC.
    # Never float (PHASE-2.3 §8, PHASE-2.6 §14). NUMERIC(12,2) rounds to the
    # cent on store; Block 2 must reject non-cent amounts before insert
    # (PHASE-2.3 §18) -- see docs/decisions/block-1-followups.md.
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    # When the financial event actually happened.
    event_date: Mapped[date] = mapped_column(Date, nullable=False)

    # When it was recorded into the system (server-generated). Named recorded_at,
    # confirmed for implementation.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id"), nullable=False
    )

    status: Mapped[TransactionStatus] = mapped_column(
        _transaction_status,
        nullable=False,
        server_default=text("'ACTIVE'::transaction_status"),
    )

    # Points at the correction that replaced this row. NULL while ACTIVE.
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("transaction.id"), nullable=True
    )

    # Idempotency reference for the originating event (PHASE-2.5 §16, PHASE-2.6 §7).
    # UNIQUE is the authoritative guard against duplicate webhooks / retries.
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Technical row-creation timestamp (audit).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_by: Mapped["Person"] = relationship(
        "Person", back_populates="transactions", foreign_keys=[created_by_id]
    )
    superseded_by: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", remote_side=[id], foreign_keys=[superseded_by_id]
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Transaction id={self.id} type={self.event_type} "
            f"amount={self.amount} status={self.status}>"
        )
