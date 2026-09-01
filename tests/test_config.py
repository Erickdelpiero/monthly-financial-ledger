"""get_database_url(): full URL vs. safely-assembled components. No DB."""

from __future__ import annotations

import pytest
from sqlalchemy import make_url

from money_ledger.config import get_database_url

_COMPONENTS = {
    "DB_HOST": "db",
    "DB_PORT": "5432",
    "DB_NAME": "money_ledger",
    "DB_USER": "money_ledger_app",
    "DB_PASSWORD": "plain-secret",
}


def _set_components(monkeypatch, **overrides) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key, value in {**_COMPONENTS, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_explicit_database_url_wins_over_components(monkeypatch) -> None:
    _set_components(monkeypatch, DB_HOST="should-be-ignored")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@realhost:5432/x")
    assert get_database_url() == "postgresql+psycopg://u:p@realhost:5432/x"


def test_assembled_from_components(monkeypatch) -> None:
    _set_components(monkeypatch)
    url = make_url(get_database_url())
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database) == ("db", 5432, "money_ledger")
    assert url.username == "money_ledger_app"
    assert url.password == "plain-secret"


@pytest.mark.parametrize(
    "password",
    [
        "p@ssw0rd",
        "a:b/c#d%e",
        "has space and @:/#%",
        "quote'and\"double",
        "trailing%",
    ],
)
def test_reserved_characters_in_password_survive_round_trip(monkeypatch, password) -> None:
    _set_components(monkeypatch, DB_PASSWORD=password)
    rendered = get_database_url()
    # the raw password must not appear unescaped in the URL string...
    assert f":{password}@" not in rendered
    # ...but it must parse back exactly.
    assert make_url(rendered).password == password


def test_missing_everything_is_a_clear_error(monkeypatch) -> None:
    _set_components(monkeypatch, DB_HOST=None, DB_NAME=None, DB_USER=None, DB_PASSWORD=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_database_url()


def test_partial_components_name_the_missing_ones(monkeypatch) -> None:
    _set_components(monkeypatch, DB_PASSWORD=None)
    with pytest.raises(RuntimeError, match="DB_PASSWORD"):
        get_database_url()
