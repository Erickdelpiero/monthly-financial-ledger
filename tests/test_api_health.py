"""GET /api/v1/health (PHASE-2.5 §18)."""

from __future__ import annotations


def test_health_is_ok_and_unauthenticated(api_client) -> None:
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_api_key(api_client) -> None:
    # no X-API-Key header at all
    assert api_client.get("/api/v1/health").status_code == 200
