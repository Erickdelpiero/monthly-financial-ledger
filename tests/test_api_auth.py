"""Service-token auth on the API (PHASE-2.5 §6, PHASE-2.9 §11)."""

from __future__ import annotations

import pytest

from tests.conftest import API_TOKEN

PROTECTED = [
    ("post", "/api/v1/transactions"),
    ("post", "/api/v1/transactions/00000000-0000-0000-0000-000000000000/corrections"),
    ("get", "/api/v1/balance"),
]


def _call(api_client, method: str, path: str, headers: dict | None = None):
    if method == "get":
        return api_client.get(path, headers=headers or {})
    return api_client.post(path, json={}, headers=headers or {})


@pytest.mark.parametrize("method, path", PROTECTED)
def test_missing_api_key_is_401(api_client, method: str, path: str) -> None:
    response = _call(api_client, method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("method, path", PROTECTED)
def test_wrong_api_key_is_401(api_client, method: str, path: str) -> None:
    response = _call(api_client, method, path, headers={"X-API-Key": "not-the-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_valid_key_passes_auth_and_reaches_the_handler(api_client) -> None:
    # Correct key -> auth passes; the empty body then fails validation (422),
    # which proves we got past the 401 guard.
    response = api_client.post(
        "/api/v1/transactions", json={}, headers={"X-API-Key": API_TOKEN}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
