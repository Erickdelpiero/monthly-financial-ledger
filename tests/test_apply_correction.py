"""apply_correction service (PHASE-2.3 §12-13; PHASE-2.5 §14; PHASE-2.6 §9)."""

from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from money_ledger.domain.errors import (
    CorrectionNotAllowed,
    DuplicateIdempotencyKey,
    InactivePerson,
    TransactionNotActive,
    TransactionNotFound,
    UnknownPerson,
)
from money_ledger.models.enums import EventType, TransactionStatus
from money_ledger.models.person import Person
from money_ledger.models.transaction import Transaction
from money_ledger.services import apply_correction, get_balance, record_transaction
from tests.conftest import make_person

TODAY = date(2026, 8, 31)


def _seed(db_session: Session, person: Person, **overrides) -> Transaction:
    kwargs = dict(
        created_by_id=person.id,
        event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("35.50"),
        description="taxi",
        event_date=date(2026, 8, 30),
        idempotency_key=f"seed-{uuid.uuid4()}",
        today=TODAY,
    )
    kwargs.update(overrides)
    row = record_transaction(db_session, **kwargs)
    db_session.flush()
    return row


def _count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Transaction)).scalar_one()


def test_correct_amount_supersedes_and_updates_balance(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person, amount=Decimal("35.50"))
    assert get_balance(db_session).net == Decimal("-35.50")

    corrected = apply_correction(
        db_session,
        target_id=original.id,
        created_by_id=person.id,
        idempotency_key="corr-1",
        amount=Decimal("40.00"),
        today=TODAY,
    )
    db_session.flush()
    db_session.expire_all()

    assert corrected.status is TransactionStatus.ACTIVE
    assert corrected.amount == Decimal("40.00")
    assert corrected.event_type is EventType.erick_gasta_para_mama  # copied
    assert corrected.description == "taxi"                          # copied

    reloaded = db_session.get(Transaction, original.id)
    assert reloaded.status is TransactionStatus.SUPERSEDED
    assert reloaded.superseded_by_id == corrected.id
    assert get_balance(db_session).net == Decimal("-40.00")


def test_correct_event_type_flips_the_sign(db_session: Session, person: Person) -> None:
    original = _seed(db_session, person, event_type=EventType.erick_gasta_para_mama,
                     amount=Decimal("50.00"))
    assert get_balance(db_session).net == Decimal("-50.00")

    apply_correction(
        db_session,
        target_id=original.id,
        created_by_id=person.id,
        idempotency_key="corr-flip",
        event_type=EventType.mama_entrega_dinero,
        today=TODAY,
    )
    db_session.flush()
    assert get_balance(db_session).net == Decimal("50.00")


def test_correct_only_description_copies_other_fields(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person, amount=Decimal("12.90"), description="farmacia")
    corrected = apply_correction(
        db_session, target_id=original.id, created_by_id=person.id,
        idempotency_key="corr-desc", description="farmacia (genérico)", today=TODAY,
    )
    db_session.flush()
    assert corrected.amount == Decimal("12.90")
    assert corrected.event_date == original.event_date
    assert corrected.description == "farmacia (genérico)"


def test_correction_writes_the_actor_id_onto_the_new_row(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person)
    corrected = apply_correction(
        db_session, target_id=original.id, created_by_id=person.id,
        idempotency_key="corr-actor", amount=Decimal("1.00"), today=TODAY,
    )
    assert corrected.created_by_id == person.id


def test_cannot_correct_another_persons_transaction(
    db_session: Session, person: Person
) -> None:
    """v1 policy (PHASE-2.10 §18.1 / §29.9): correct only your own entries."""
    mama = make_person(name="mama")
    db_session.add(mama)
    db_session.flush()

    original = _seed(db_session, person)  # registered by `person`
    with pytest.raises(CorrectionNotAllowed):
        apply_correction(
            db_session, target_id=original.id, created_by_id=mama.id,
            idempotency_key="corr-foreign", amount=Decimal("1.00"), today=TODAY,
        )
    db_session.expire_all()
    assert db_session.get(Transaction, original.id).status is TransactionStatus.ACTIVE


def test_correction_actor_must_exist_and_be_active(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person)
    with pytest.raises(UnknownPerson):
        apply_correction(db_session, target_id=original.id, created_by_id=uuid.uuid4(),
                         idempotency_key="corr-x1", amount=Decimal("1.00"), today=TODAY)

    inactive = make_person(name="inactive")
    inactive.is_active = False
    db_session.add(inactive)
    db_session.flush()
    with pytest.raises(InactivePerson):
        apply_correction(db_session, target_id=original.id, created_by_id=inactive.id,
                         idempotency_key="corr-x2", amount=Decimal("1.00"), today=TODAY)


def test_chained_corrections_only_the_tail_is_active(
    db_session: Session, person: Person
) -> None:
    a = _seed(db_session, person, amount=Decimal("35.50"))
    b = apply_correction(db_session, target_id=a.id, created_by_id=person.id,
                         idempotency_key="chain-b", amount=Decimal("40.00"), today=TODAY)
    db_session.flush()
    c = apply_correction(db_session, target_id=b.id, created_by_id=person.id,
                         idempotency_key="chain-c", amount=Decimal("42.00"), today=TODAY)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Transaction, a.id).status is TransactionStatus.SUPERSEDED
    assert db_session.get(Transaction, b.id).status is TransactionStatus.SUPERSEDED
    assert db_session.get(Transaction, c.id).status is TransactionStatus.ACTIVE
    assert get_balance(db_session).net == Decimal("-42.00")


def test_correcting_a_superseded_row_is_rejected(db_session: Session, person: Person) -> None:
    a = _seed(db_session, person)
    apply_correction(db_session, target_id=a.id, created_by_id=person.id,
                     idempotency_key="sup-b", amount=Decimal("40.00"), today=TODAY)
    db_session.flush()
    with pytest.raises(TransactionNotActive):
        apply_correction(db_session, target_id=a.id, created_by_id=person.id,
                         idempotency_key="sup-c", amount=Decimal("50.00"), today=TODAY)


def test_correcting_a_missing_row_is_rejected(db_session: Session, person: Person) -> None:
    with pytest.raises(TransactionNotFound):
        apply_correction(db_session, target_id=uuid.uuid4(), created_by_id=person.id,
                         idempotency_key="missing", amount=Decimal("1.00"), today=TODAY)


def test_same_key_same_payload_replays_the_same_correction(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person)
    first = apply_correction(db_session, target_id=original.id, created_by_id=person.id,
                             idempotency_key="replay", amount=Decimal("40.00"), today=TODAY)
    db_session.flush()
    again = apply_correction(db_session, target_id=original.id, created_by_id=person.id,
                             idempotency_key="replay", amount=Decimal("40.00"), today=TODAY)
    assert again.id == first.id
    assert _count(db_session) == 2  # original + one correction


def test_same_key_same_target_different_payload_conflicts(
    db_session: Session, person: Person
) -> None:
    original = _seed(db_session, person)
    apply_correction(db_session, target_id=original.id, created_by_id=person.id,
                     idempotency_key="pl", amount=Decimal("40.00"), today=TODAY)
    db_session.flush()
    with pytest.raises(DuplicateIdempotencyKey):
        apply_correction(db_session, target_id=original.id, created_by_id=person.id,
                         idempotency_key="pl", amount=Decimal("41.00"), today=TODAY)


def test_reusing_a_key_for_a_different_target_conflicts(
    db_session: Session, person: Person
) -> None:
    a = _seed(db_session, person)
    other = _seed(db_session, person)
    apply_correction(db_session, target_id=a.id, created_by_id=person.id,
                     idempotency_key="shared", amount=Decimal("40.00"), today=TODAY)
    db_session.flush()
    with pytest.raises(DuplicateIdempotencyKey):
        apply_correction(db_session, target_id=other.id, created_by_id=person.id,
                         idempotency_key="shared", amount=Decimal("40.00"), today=TODAY)


def test_correction_is_atomic_on_partial_failure(db_session: Session, person: Person) -> None:
    """If the target flip fails, the new row must not survive either."""
    original = _seed(db_session, person, amount=Decimal("35.50"))
    before = _count(db_session)
    real_flush = db_session.flush
    calls = {"n": 0}

    def flaky_flush(*args, **kwargs):
        calls["n"] += 1
        result = real_flush(*args, **kwargs)
        if calls["n"] == 2:  # after the new row insert, during the target flip
            raise RuntimeError("boom")
        return result

    with mock.patch.object(db_session, "flush", side_effect=flaky_flush):
        with pytest.raises(RuntimeError):
            apply_correction(db_session, target_id=original.id, created_by_id=person.id,
                             idempotency_key="atomic", amount=Decimal("40.00"), today=TODAY)

    db_session.expire_all()
    assert _count(db_session) == before
    reloaded = db_session.get(Transaction, original.id)
    assert reloaded.status is TransactionStatus.ACTIVE
    assert reloaded.superseded_by_id is None


def test_concurrent_same_key_correction_is_deterministic(
    engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    """Two real transactions racing the same key + target return the same
    correction, create exactly one, and never surface TransactionNotActive."""
    setup = session_factory()
    person = make_person()
    setup.add(person)
    setup.flush()
    original = record_transaction(
        setup, created_by_id=person.id, event_type=EventType.erick_gasta_para_mama,
        amount=Decimal("35.50"), description="taxi", event_date=date(2026, 8, 30),
        idempotency_key=f"conc-seed-{uuid.uuid4()}", today=TODAY,
    )
    setup.commit()
    original_id, person_id = original.id, person.id
    setup.close()

    key = f"conc-{uuid.uuid4()}"
    barrier = threading.Barrier(2)
    results: dict[int, object] = {}

    def worker(n: int) -> None:
        s = session_factory()
        try:
            barrier.wait(timeout=5)
            row = apply_correction(
                s, target_id=original_id, created_by_id=person_id,
                idempotency_key=key, amount=Decimal("40.00"), today=TODAY,
            )
            s.commit()
            results[n] = row.id
        except Exception as exc:  # noqa: BLE001 - recorded for the assertion
            s.rollback()
            results[n] = exc
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    try:
        assert not any(isinstance(v, Exception) for v in results.values()), results
        assert results[0] == results[1]
        with engine.connect() as conn:
            n_corr = conn.execute(
                select(func.count()).select_from(Transaction).where(
                    Transaction.idempotency_key == key
                )
            ).scalar_one()
            n_active = conn.execute(
                select(func.count()).select_from(Transaction).where(
                    Transaction.status == TransactionStatus.ACTIVE
                )
            ).scalar_one()
        assert n_corr == 1
        assert n_active == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE transaction, person CASCADE"))
