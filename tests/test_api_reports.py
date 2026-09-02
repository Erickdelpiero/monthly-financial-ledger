"""GET /reports/weekly, /reports/monthly, /reports/monthly/image
(PHASE-2.5 §19-20, PHASE-2.8). ``X-API-Key`` only; the bilateral balance is
shared, so no ``telegram_user_id`` (PHASE-2.8 §2)."""

from __future__ import annotations

import uuid

from tests.conftest import API_TOKEN

AUTH = {"X-API-Key": API_TOKEN}
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _record(api_client, tg_id, *, raw_text, event_date,
            event_type="erick_gasta_para_mama") -> None:
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


# --- weekly -----------------------------------------------------------------

def test_weekly_no_debt(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/weekly", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "📊 Saldo actual\n\nNo hay deuda pendiente.\nSaldo: S/ 0.00"
    assert body["balance"]["direction"] == "no_debt"


def test_weekly_reflects_direction(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 100 compras",
            event_date="2026-08-10", event_type="mama_entrega_dinero")
    body = api_client.get("/api/v1/reports/weekly", headers=AUTH).json()
    assert body["text"] == "📊 Saldo actual\n\nErick debe a Mamá: S/ 100.00"
    assert body["balance"]["direction"] == "erick_owes_mama"


def test_weekly_requires_api_key(api_client, people) -> None:
    assert api_client.get("/api/v1/reports/weekly").status_code == 401


# --- monthly (JSON) -------------------------------------------------------

def test_monthly_shape_and_movements(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 70 super", event_date="2026-08-05")
    _record(api_client, people["mama"], raw_text="S/ 30 efectivo",
            event_date="2026-08-08", event_type="mama_entrega_dinero")

    r = api_client.get("/api/v1/reports/monthly",
                       params={"year": 2026, "month": 8}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2026 and body["month"] == 8
    assert body["period"] == "Agosto 2026"
    assert "balance" in body
    assert len(body["movements"]) == 2
    m = body["movements"][0]
    assert set(m) == {
        "event_date", "recorded_at", "person", "event_type", "movement",
        "amount", "description",
    }
    assert m["event_date"] == "2026-08-05"
    assert m["person"] == "Erick"
    assert m["movement"] == "Yo gasté para mamá"
    assert m["amount"] == "70.00"


def test_monthly_empty_month(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 5 x", event_date="2026-08-10")
    r = api_client.get("/api/v1/reports/monthly",
                       params={"year": 2026, "month": 3}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["movements"] == []


def test_monthly_missing_params_is_422(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/monthly", headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_monthly_bad_month_is_422(api_client, people) -> None:
    for month in (0, 13, 99):
        r = api_client.get("/api/v1/reports/monthly",
                           params={"year": 2026, "month": month}, headers=AUTH)
        assert r.status_code == 422, month


def test_monthly_requires_api_key(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/monthly", params={"year": 2026, "month": 8})
    assert r.status_code == 401


# --- monthly (PNG) ------------------------------------------------------

def test_monthly_image_returns_png(api_client, people) -> None:
    _record(api_client, people["erick"], raw_text="S/ 70 super", event_date="2026-08-05")
    r = api_client.get("/api/v1/reports/monthly/image",
                       params={"year": 2026, "month": 8}, headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content.startswith(_PNG_MAGIC)
    assert len(r.content) > 1000


def test_monthly_image_empty_month_is_png(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/monthly/image",
                       params={"year": 2026, "month": 4}, headers=AUTH)
    assert r.status_code == 200
    assert r.content.startswith(_PNG_MAGIC)


def test_monthly_image_bad_params_is_422(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/monthly/image",
                       params={"year": 2026, "month": 99}, headers=AUTH)
    assert r.status_code == 422


def test_monthly_image_requires_api_key(api_client, people) -> None:
    r = api_client.get("/api/v1/reports/monthly/image",
                       params={"year": 2026, "month": 8})
    assert r.status_code == 401
