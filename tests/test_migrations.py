"""Alembic migration behaviour (PHASE-2.6 §15, PHASE-2.9 §13).

Covers: build-from-scratch, full downgrade, upgrade/downgrade/upgrade round
trip, single linear head, and that the resulting schema matches the models.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, make_url, text
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_TABLES = {"person", "transaction"}

EXPECTED_TRANSACTION_COLUMNS = {
    "id",
    "event_type",
    "amount",
    "description",
    "event_date",
    "recorded_at",
    "created_by_id",
    "status",
    "superseded_by_id",
    "idempotency_key",
    "created_at",
}
EXPECTED_PERSON_COLUMNS = {
    "id",
    "telegram_user_id",
    "name",
    "is_active",
    "created_at",
}
EXPECTED_TRANSACTION_CHECKS = {
    "ck_transaction_amount_positive",
    "ck_transaction_description_not_blank",
    "ck_transaction_idempotency_key_not_blank",
    "ck_transaction_no_self_supersede",
    "ck_transaction_status_supersede_consistency",
}


@pytest.fixture(autouse=True)
def _restore_head(alembic_config: Config, engine: Engine):
    """Whatever a test does to the schema, leave it back at head afterwards."""
    yield
    command.upgrade(alembic_config, "head")


def _enum_types_present(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT typname FROM pg_type "
                "WHERE typname IN ('event_type', 'transaction_status')"
            )
        ).scalars()
        return set(rows)


APPEND_ONLY_FUNCTIONS = ("ledger_forbid_delete", "ledger_guard_update")


def _append_only_functions_present(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            fn
            for fn in APPEND_ONLY_FUNCTIONS
            if conn.execute(text("SELECT to_regproc(:f)"), {"f": fn}).scalar()
        }


def test_single_linear_head(alembic_config: Config) -> None:
    script = ScriptDirectory.from_config(alembic_config)
    assert len(script.get_heads()) == 1


def test_head_is_the_latest_revision(alembic_config: Config) -> None:
    script = ScriptDirectory.from_config(alembic_config)
    assert script.get_current_head() == "0002_append_only_delete_guard"


def test_upgrade_from_empty_creates_core_tables(
    alembic_config: Config, engine: Engine
) -> None:
    command.downgrade(alembic_config, "base")
    assert not (CORE_TABLES & set(inspect(engine).get_table_names()))

    command.upgrade(alembic_config, "head")
    tables = set(inspect(engine).get_table_names())
    assert CORE_TABLES <= tables
    assert "alembic_version" in tables


def test_downgrade_removes_tables_types_and_guards(
    alembic_config: Config, engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")
    assert _enum_types_present(engine) == {"event_type", "transaction_status"}
    assert _append_only_functions_present(engine) == set(APPEND_ONLY_FUNCTIONS)

    command.downgrade(alembic_config, "base")
    remaining = set(inspect(engine).get_table_names())
    assert not (CORE_TABLES & remaining)
    assert _enum_types_present(engine) == set()
    assert _append_only_functions_present(engine) == set()


def test_upgrade_tolerates_percent_in_the_db_url(
    alembic_config: Config, engine: Engine, database_url: str
) -> None:
    """Regression: a random password can contain '%', and URL.create
    percent-encodes reserved characters. The URL must not go through
    configparser interpolation (env.py used to `set_main_option` it, which
    raised `ValueError: invalid interpolation syntax`).
    """
    percent_url = (
        make_url(database_url)
        .set(password="pa%ss%2Fword%wild")
        .render_as_string(hide_password=False)
    )
    assert "%" in percent_url

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.attributes["db_url"] = percent_url

    command.downgrade(alembic_config, "base")
    command.upgrade(cfg, "head")  # must not raise ValueError
    assert CORE_TABLES <= set(inspect(engine).get_table_names())


def test_downgrade_one_step_keeps_the_schema(
    alembic_config: Config, engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0001_initial_schema")
    assert CORE_TABLES <= set(inspect(engine).get_table_names())
    assert _append_only_functions_present(engine) == set()


def test_roundtrip_upgrade_downgrade_upgrade(
    alembic_config: Config, engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert CORE_TABLES <= set(inspect(engine).get_table_names())


def test_transaction_columns_match_models(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    insp = inspect(engine)
    assert {c["name"] for c in insp.get_columns("transaction")} == EXPECTED_TRANSACTION_COLUMNS
    assert {c["name"] for c in insp.get_columns("person")} == EXPECTED_PERSON_COLUMNS


def test_amount_column_is_numeric_12_2(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    amount = next(
        c for c in inspect(engine).get_columns("transaction") if c["name"] == "amount"
    )
    assert amount["type"].precision == 12
    assert amount["type"].scale == 2


def test_named_constraints_present(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    insp = inspect(engine)

    txn_checks = {c["name"] for c in insp.get_check_constraints("transaction")}
    assert EXPECTED_TRANSACTION_CHECKS <= txn_checks

    txn_uniques = {u["name"] for u in insp.get_unique_constraints("transaction")}
    assert {
        "uq_transaction_idempotency_key",
        "uq_transaction_superseded_by_id",
    } <= txn_uniques

    txn_fks = {fk["name"] for fk in insp.get_foreign_keys("transaction")}
    assert {
        "fk_transaction_created_by_id_person",
        "fk_transaction_superseded_by_id_transaction",
    } <= txn_fks

    person_uniques = {u["name"] for u in insp.get_unique_constraints("person")}
    assert "uq_person_telegram_user_id" in person_uniques

    person_checks = {c["name"] for c in insp.get_check_constraints("person")}
    assert {
        "ck_person_telegram_user_id_not_blank",
        "ck_person_name_not_blank",
    } <= person_checks


def test_expected_indexes_present(alembic_config: Config, engine: Engine) -> None:
    command.upgrade(alembic_config, "head")
    names = {ix["name"] for ix in inspect(engine).get_indexes("transaction")}
    assert {
        "ix_transaction_status",
        "ix_transaction_event_date",
        "ix_transaction_created_by_id",
    } <= names
    # superseded_by_id lookups are served by the UNIQUE constraint's index.
