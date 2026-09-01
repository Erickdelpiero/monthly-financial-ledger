"""Resolve a Telegram user to a Person (PHASE-2.5 §7, PHASE-2.11 §4.1).

n8n never sends a trusted ``person_id``. An unknown or inactive
``telegram_user_id`` is rejected here -- no ``Person`` or ``Transaction`` row is
created (PHASE-2.6 §12).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from money_ledger.api.errors import UnknownTelegramUser
from money_ledger.models.person import Person


def resolve_person(session: Session, telegram_user_id: str) -> Person:
    person = session.execute(
        select(Person).where(Person.telegram_user_id == telegram_user_id)
    ).scalar_one_or_none()
    if person is None:
        raise UnknownTelegramUser(
            f"telegram_user_id {telegram_user_id!r} is not registered"
        )
    if not person.is_active:
        raise UnknownTelegramUser(
            f"telegram_user_id {telegram_user_id!r} is not active"
        )
    return person
