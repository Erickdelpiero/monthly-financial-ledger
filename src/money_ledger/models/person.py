"""Person entity (PHASE-2.3 §7.1).

Exactly two people exist in v1, but identity is stored as data — it is never
hard-coded into financial logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from money_ledger.db.base import Base

if TYPE_CHECKING:
    from money_ledger.models.transaction import Transaction


class Person(Base):
    __tablename__ = "person"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(telegram_user_id)) > 0",
            name="telegram_user_id_not_blank",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="created_by",
        foreign_keys="Transaction.created_by_id",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Person id={self.id} name={self.name!r} active={self.is_active}>"
