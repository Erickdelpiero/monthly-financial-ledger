"""POST /api/v1/transactions/{id}/corrections (PHASE-2.5 §14)."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.conftest import API_TOKEN

AUTH = {"X-API-Key": API_TOKEN}


def _record(api_client, people, **overrides) -> str:
    body = {
        "telegram_user_id": people["erick"],
        "event_type": "erick_gasta_para_mama",
        "event_date": "2026-08-30",
        "idempotency_key": f"tg:{uuid.uuid4()}",
        "raw_text": "S/ 35.50 taxi",
    }
    body.update(overrides)
    r = api_client.post("/api/v1/transactions", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()["transaction"]["id"]


def _correct(api_client, txn_id: str, **body):
    return api_client.post(
        f"/api/v1/transactions/{txn_id}/corrections", json=body, headers=AUTH
    )


def test_correct_amount_via_raw_text(api_client, people) -> None:
    txn_id = _record(api_client, people)
    r = _correct(
        api_client, txn_id,
        telegram_user_id=people["erick"],
        idempotency_key="tg:c1",
        raw_text="S/ 40.00 taxi",
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["correction"]["amount"] == "40.00"
    assert data["correction"]["status"] == "ACTIVE"
    assert data["balance"] == {
        "balance": "40.00",
        "currency": "PEN",
        "direction": "mama_owes_erick",
    }


def test_correct_event_type_flips_direction(api_client, people) -> None:
    txn_id = _record(api_client, people, raw_text="S/ 50 algo")
    r = _correct(
        api_client, txn_id,
        telegram_user_id=people["erick"],
        idempotency_key="tg:c2",
        event_type="mama_entrega_dinero",
    )
    assert r.status_code == 200
    assert r.json()["balance"]["direction"] == "erick_owes_mama"


def test_correction_carries_the_actors_person_id(api_client, people, engine) -> None:
    txn_id = _record(api_client, people)  # registered by erick
    r = _correct(
        api_client, txn_id,
        telegram_user_id=people["erick"],
        idempotency_key="tg:c3",
        raw_text="S/ 40.00 taxi",
    )
    assert r.status_code == 200
    with engine.begin() as conn:
        erick_id = str(
            conn.execute(
                text("SELECT id FROM person WHERE telegram_user_id = :t"),
                {"t": people["erick"]},
            ).scalar_one()
        )
    assert r.json()["correction"]["created_by"] == erick_id


def test_cannot_correct_another_users_transaction(api_client, people) -> None:
    """v1 policy (PHASE-2.10 §18.1 / §29.9): each person corrects only their own."""
    txn_id = _record(api_client, people)  # registered by erick
    r = _correct(
        api_client, txn_id,
        telegram_user_id=people["mama"],  # mamá tries
        idempotency_key="tg:foreign",
        raw_text="S/ 40.00 taxi",
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CORRECTION_NOT_ALLOWED"


def test_correct_only_amount_keeps_description(api_client, people) -> None:
    txn_id = _record(api_client, people, raw_text="S/ 35.50 taxi")
    r = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                 idempotency_key="tg:only-amt", amount="40.00")
    assert r.status_code == 200, r.text
    assert r.json()["correction"]["amount"] == "40.00"
    assert r.json()["correction"]["description"] == "taxi"


def test_correct_only_description_keeps_amount(api_client, people) -> None:
    txn_id = _record(api_client, people, raw_text="S/ 35.50 taxi")
    r = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                 idempotency_key="tg:only-desc", description="taxi al aeropuerto")
    assert r.status_code == 200, r.text
    assert r.json()["correction"]["amount"] == "35.50"
    assert r.json()["correction"]["description"] == "taxi al aeropuerto"


def test_empty_correction_body_is_422(api_client, people) -> None:
    txn_id = _record(api_client, people)
    r = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                 idempotency_key="tg:empty")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_correction_raw_text_and_structured_together_is_422(api_client, people) -> None:
    txn_id = _record(api_client, people)
    r = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                 idempotency_key="tg:both", raw_text="S/ 40 taxi", amount="99.00")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_correcting_missing_transaction_is_404(api_client, people) -> None:
    r = _correct(
        api_client, str(uuid.uuid4()),
        telegram_user_id=people["erick"],
        idempotency_key="tg:c4",
        amount="1.00",
        description="x",
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"


def test_correcting_a_superseded_transaction_is_409(api_client, people) -> None:
    txn_id = _record(api_client, people)
    first = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                     idempotency_key="tg:c5a", amount="40.00", description="taxi")
    assert first.status_code == 200
    r = _correct(api_client, txn_id, telegram_user_id=people["erick"],
                 idempotency_key="tg:c5b", amount="50.00", description="taxi")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "TRANSACTION_NOT_ACTIVE"


def test_malformed_uuid_path_is_422(api_client, people) -> None:
    r = _correct(api_client, "not-a-uuid", telegram_user_id=people["erick"],
                 idempotency_key="tg:c6", amount="1.00", description="x")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_correction_requires_auth(api_client, people) -> None:
    txn_id = _record(api_client, people)
    r = api_client.post(
        f"/api/v1/transactions/{txn_id}/corrections",
        json={"telegram_user_id": people["erick"], "idempotency_key": "tg:c7",
              "amount": "40.00", "description": "taxi"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_correction_idempotent_replay(api_client, people) -> None:
    txn_id = _record(api_client, people)
    body = dict(telegram_user_id=people["erick"], idempotency_key="tg:c8",
                amount="40.00", description="taxi")
    first = _correct(api_client, txn_id, **body)
    second = _correct(api_client, txn_id, **body)
    assert first.status_code == second.status_code == 200
    assert first.json()["correction"]["id"] == second.json()["correction"]["id"]
