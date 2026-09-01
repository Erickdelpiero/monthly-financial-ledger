"""Minimal configuration for Block 1: just the database URL.

A fuller settings layer (API keys, LLM, Telegram) arrives with later blocks;
see architecture/PHASE-2.11 for the variable names.
"""

from __future__ import annotations

import os

from sqlalchemy import URL

try:  # optional convenience in local dev / tests
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # pragma: no cover - dotenv is a declared dependency
    pass

_COMPONENT_VARS = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def get_database_url() -> str:
    """Return the SQLAlchemy URL for the application database.

    Prefers a full ``DATABASE_URL``. Otherwise it is assembled from the
    components ``DB_HOST`` / ``DB_PORT`` / ``DB_NAME`` / ``DB_USER`` /
    ``DB_PASSWORD`` via ``sqlalchemy.URL.create`` -- which percent-encodes the
    password, so a strong password containing ``@ : / # %`` is safe (Compose
    passes the components, never a hand-built URL string).

    Raises a clear error instead of silently falling back to a default.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    missing = [v for v in _COMPONENT_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            "Set DATABASE_URL, or all of "
            "DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD "
            f"(missing: {', '.join(missing)})."
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT") or 5432),
        database=os.environ["DB_NAME"],
    ).render_as_string(hide_password=False)


def get_api_token() -> str:
    """Return the internal service token n8n presents as ``X-API-Key``.

    It is a service credential, not an end-user identity, and never the
    database password (PHASE-2.5 §6, PHASE-2.11 §3).
    """
    token = os.environ.get("API_INTERNAL_TOKEN")
    if not token:
        raise RuntimeError(
            "API_INTERNAL_TOKEN is not set. Copy .env.example to .env and set a "
            "value (a distinct one per environment)."
        )
    return token
