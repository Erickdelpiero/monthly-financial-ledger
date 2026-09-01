"""POST /api/v1/transactions and GET /api/v1/balance (PHASE-2.5 §8-13)."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import API_TOKEN, RecordingLLM, build_api_client

AUTH = {"X-API-Key": API_TOKEN}


def _body(people: dict, **overrides) -> dict:
    body = {
        "telegram_user_id": people["erick"],
        "event_type": "erick_gasta_para_mama",
        "event_date": "2026-08-30",
        "idempotency_key": f"tg:{uuid.uuid4()}",
        "raw_text": "S/ 35.50 taxi",
    }
    body.update(overrides)
    return body


def _post(api_client, body: dict):
    return api_client.post("/api/v1/transactions", json=body, headers=AUTH)


def test_happy_path_with_raw_text(api_client, people) -> None:
    r = _post(api_client, _body(people))
    assert r.status_code == 200
    data = r.json()
    txn = data["transaction"]
    assert txn["amount"] == "35.50"
    assert txn["description"] == "taxi"
    assert txn["event_type"] == "erick_gasta_para_mama"
    assert txn["status"] == "ACTIVE"
    assert txn["parse_source"] == "deterministic"
    assert data["balance"] == {
        "balance": "35.50",
        "currency": "PEN",
        "direction": "mama_owes_erick",
    }


def test_happy_path_with_structured_amount(api_client, people) -> None:
    body = _body(people, raw_text=None, amount="100.00", description="compras",
                 event_type="mama_entrega_dinero")
    r = _post(api_client, body)
    assert r.status_code == 200
    assert r.json()["transaction"]["amount"] == "100.00"
    assert r.json()["balance"]["direction"] == "erick_owes_mama"


def test_unknown_telegram_user_is_403(api_client, people) -> None:
    r = _post(api_client, _body(people, telegram_user_id="tg-nobody"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "UNKNOWN_TELEGRAM_USER"


def test_inactive_person_is_403(api_client, people, engine) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE person SET is_active = false WHERE telegram_user_id = :t"),
            {"t": people["erick"]},
        )
    r = _post(api_client, _body(people))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "UNKNOWN_TELEGRAM_USER"


def test_invalid_event_type_is_422(api_client, people) -> None:
    r = _post(api_client, _body(people, event_type="mama_regala"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_EVENT_TYPE"


@pytest.mark.parametrize("bad_date", ["2026-13-40", "hoy", "30/08/2026"])
def test_malformed_event_date_is_422(api_client, people, bad_date: str) -> None:
    r = _post(api_client, _body(people, event_date=bad_date))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_EVENT_DATE"


def test_future_event_date_is_422(api_client, people) -> None:
    r = _post(api_client, _body(people, event_date="2099-01-01"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_EVENT_DATE"


def test_unparseable_raw_text_is_422_parser_failed(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text="me gasté un montón"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PARSER_FAILED"


def test_foreign_currency_raw_text_is_422_parser_failed(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text="USD 50 taxi"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PARSER_FAILED"


def test_zero_amount_is_422_invalid_amount(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text="0 taxi"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_AMOUNT"


@pytest.mark.parametrize("forbidden", ["signed_effect", "signed_amount", "balance", "person_id"])
def test_forbidden_fields_are_rejected(api_client, people, forbidden: str) -> None:
    r = _post(api_client, _body(people, **{forbidden: "x"}))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_required_field_is_422(api_client, people) -> None:
    body = _body(people)
    del body["event_type"]
    r = _post(api_client, body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_neither_raw_text_nor_structured_is_422(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text=None))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_raw_text_and_structured_together_is_422(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text="S/ 35 taxi", amount="999.00",
                                description="x"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_signed_amount_in_raw_text_is_422_parser_failed(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text="-35.50 taxi"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PARSER_FAILED"


def test_negative_structured_amount_is_422_invalid_amount(api_client, people) -> None:
    r = _post(api_client, _body(people, raw_text=None, amount="-35.50",
                                description="taxi"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_AMOUNT"


def test_idempotent_replay_returns_same_transaction(api_client, people) -> None:
    body = _body(people, idempotency_key="tg:fixed-1")
    first = _post(api_client, body)
    second = _post(api_client, body)
    assert first.status_code == second.status_code == 200
    assert first.json()["transaction"]["id"] == second.json()["transaction"]["id"]
    # balance did not double
    assert second.json()["balance"]["balance"] == "35.50"


def test_idempotency_conflict_on_different_request_is_409(api_client, people) -> None:
    # Same key but a different event_type -> a genuine conflict (detected from
    # cheap fields, without re-parsing).
    body = _body(people, idempotency_key="tg:fixed-2")
    _post(api_client, body)
    r = _post(api_client, {**body, "event_type": "mama_entrega_dinero"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_IDEMPOTENCY_KEY"


def test_replay_with_altered_raw_text_still_replays_without_reparsing(api_client, people) -> None:
    # Same key, same user/type/date: a retry whose raw_text was mangled in
    # transit must return the stored transaction, not re-parse (PHASE-2.9 §6.3).
    body = _body(people, idempotency_key="tg:fixed-3")
    first = _post(api_client, body)
    second = _post(api_client, {**body, "raw_text": "$$$ corrupted 9 9 9"})
    assert first.status_code == second.status_code == 200
    assert first.json()["transaction"]["id"] == second.json()["transaction"]["id"]
    assert second.json()["transaction"]["amount"] == "35.50"  # unchanged
    assert second.json()["balance"]["balance"] == "35.50"


def test_idempotent_replay_does_not_invoke_the_llm(database_url, engine, people) -> None:
    """A repeated key returns the stored row without touching the parser/LLM
    (PHASE-2.9 §6.3)."""
    llm = RecordingLLM(result={"amount": "42.00", "description": "algo"})
    with build_api_client(database_url, engine, llm=llm) as client:
        body = {
            "telegram_user_id": people["erick"],
            "event_type": "erick_gasta_para_mama",
            "event_date": "2026-08-30",
            "idempotency_key": "tg:llm-replay",
            "raw_text": "gasté algo raro que el parser no entiende",
        }
        first = client.post("/api/v1/transactions", json=body, headers=AUTH)
        second = client.post("/api/v1/transactions", json=body, headers=AUTH)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["transaction"]["id"] == second.json()["transaction"]["id"]
    assert llm.calls == ["gasté algo raro que el parser no entiende"]  # once, not twice


def test_foreign_currency_never_reaches_the_llm(database_url, engine, people) -> None:
    llm = RecordingLLM(result={"amount": "50.00", "description": "taxi"})
    with build_api_client(database_url, engine, llm=llm) as client:
        body = {
            "telegram_user_id": people["erick"],
            "event_type": "erick_gasta_para_mama",
            "event_date": "2026-08-30",
            "idempotency_key": "tg:usd",
            "raw_text": "USD 50 taxi",
        }
        r = client.post("/api/v1/transactions", json=body, headers=AUTH)

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PARSER_FAILED"
    assert llm.calls == []


def test_balance_endpoint_reflects_recorded_transactions(api_client, people) -> None:
    _post(api_client, _body(people, event_type="mama_entrega_dinero", raw_text="S/ 100 x",
                            idempotency_key="tg:b1"))
    _post(api_client, _body(people, event_type="erick_gasta_para_mama", raw_text="S/ 30 y",
                            idempotency_key="tg:b2"))
    r = api_client.get("/api/v1/balance", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"balance": "70.00", "currency": "PEN", "direction": "erick_owes_mama"}
