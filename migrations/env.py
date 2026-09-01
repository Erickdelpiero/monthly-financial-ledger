"""Alembic environment.

URL resolution order:
  1. ``config.attributes["db_url"]`` set by a caller (the test suite);
  2. otherwise ``get_database_url()`` (DATABASE_URL, or DB_* components).

The URL is never routed through ``Config.set_main_option`` / the configparser
section: a password containing ``%`` (random passwords, or the percent-encoding
that ``sqlalchemy.URL.create`` applies to reserved characters) would trigger
``ValueError: invalid interpolation syntax``. It is passed straight to
``create_engine`` / ``context.configure(url=...)`` instead.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Make ``src/`` importable when Alembic is run from the repo root.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from money_ledger.config import get_database_url  # noqa: E402
from money_ledger.db.base import Base  # noqa: E402
import money_ledger.models  # noqa: E402,F401  (registers models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_url = config.attributes.get("db_url") or get_database_url()

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url, poolclass=pool.NullPool, future=True)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
