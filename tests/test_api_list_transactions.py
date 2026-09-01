"""GET /api/v1/transactions — the correction picker's list (PHASE-2.10 §18.1)."""

from __future__ import annotations

import uuid

from tests.conftest import API_TOKEN

AUTH = {"X-API-Key": API_TOKEN}


def _record(api_client, tg_id: str, *, raw_text: str, event_date: str,
            event_type: str = "erick_gasta_para_mama") -> str:
    r = api_client.post(
        "/api/v1/transactions",
        json={
            "telegram_user_id": tg_id,
            "event_type": event_type,
            "event_date": event_date,
            "idempotency_key": f"tg:{uuid.uuid4()}",
            "raw_text": raw_text,
        },
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    return r.json()["transaction"]["id"]


def _list(api_client, tg_id: str, **params):
    return api_client.get(
        "/api/v1/transactions",
        params={"telegram_user_id": tg_id, **params},
        headers=AUTH,
    )


def test_lists_the_users_active_rows_newest_first(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 10 uno", event_date="2026-08-25")
    _record(api_client, people["erick"], raw_text="S/ 20 tres", event_date="2026-08-30")
    _record(api_client, people["erick"], raw_text="S/ 15 dos", event_date="2026-08-27")

    r = _list(api_client, people["erick"])
    assert r.status_code == 200
    rows = r.json()["transactions"]
    assert [row["description"] for row in rows] == ["tres", "dos", "uno"]
    assert all(row["status"] == "ACTIVE" for row in rows)


def test_respects_limit(api_client, people) -> None:
    for i in range(4):
        _record(api_client, people["erick"], raw_text=f"S/ {i + 1} compra",
                event_date="2026-08-30")
    r = _list(api_client, people["erick"], limit=2)
    assert len(r.json()["transactions"]) == 2


def test_only_the_requested_users_rows(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 10 erick", event_date="2026-08-30")
    _record(api_client, people["mama"], raw_text="S/ 20 mama", event_date="2026-08-30",
            event_type="mama_entrega_dinero")

    erick_rows = _list(api_client, people["erick"]).json()["transactions"]
    mama_rows = _list(api_client, people["mama"]).json()["transactions"]
    assert [r["description"] for r in erick_rows] == ["erick"]
    assert [r["description"] for r in mama_rows] == ["mama"]


def test_status_filter(api_client, people) -> None:
    txn_id = _record(api_client, people["erick"], raw_text="S/ 10 original",
                     event_date="2026-08-30")
    api_client.post(
        f"/api/v1/transactions/{txn_id}/corrections",
        json={"telegram_user_id": people["erick"], "idempotency_key": "tg:corr",
              "raw_text": "S/ 12 corregido"},
        headers=AUTH,
    )

    active = _list(api_client, people["erick"], status="active").json()["transactions"]
    superseded = _list(api_client, people["erick"], status="superseded").json()["transactions"]
    every = _list(api_client, people["erick"], status="all").json()["transactions"]
    assert [r["description"] for r in active] == ["corregido"]
    assert [r["description"] for r in superseded] == ["original"]
    assert len(every) == 2


def test_empty_result(api_client, people) -> None:
    assert _list(api_client, people["erick"]).json() == {"transactions": []}


def test_unknown_user_is_403(api_client, people) -> None:
    r = _list(api_client, "tg-nobody")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "UNKNOWN_TELEGRAM_USER"


def test_requires_api_key(api_client, people) -> None:
    r = api_client.get("/api/v1/transactions",
                       params={"telegram_user_id": people["erick"]})
    assert r.status_code == 401


def test_bad_status_is_422(api_client, people) -> None:
    r = _list(api_client, people["erick"], status="nonsense")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_limit_out_of_range_is_422(api_client, people) -> None:
    assert _list(api_client, people["erick"], limit=0).status_code == 422
    assert _list(api_client, people["erick"], limit=99).status_code == 422
