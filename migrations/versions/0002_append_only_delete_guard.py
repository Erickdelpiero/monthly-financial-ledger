"""append-only guard: DELETE forbidden, UPDATE limited to the correction step

Revision ID: 0002_append_only_delete_guard
Revises: 0001_initial_schema
Create Date: 2026-08-31

F2 (docs/decisions/block-1-followups.md): the ledger is append-only. Corrections
create a new row and mark the old one SUPERSEDED (PHASE-2.3 §9, PHASE-2.6 §10);
a ledger row is never physically deleted, and an existing row can change in
exactly one way: the ACTIVE -> SUPERSEDED transition performed by a correction.

Two triggers on `transaction`:

  * BEFORE DELETE  -> always raises.
  * BEFORE UPDATE  -> allowed only when
        OLD.status = ACTIVE, NEW.status = SUPERSEDED,
        OLD.superseded_by_id IS NULL, NEW.superseded_by_id IS NOT NULL,
        every other column unchanged,
        and the new successor row is itself ACTIVE.
    The last clause makes forked *and* cyclic chains impossible: closing a cycle
    would require pointing at an already-SUPERSEDED row.

The complementary column-scoped grants on the production app role live in
scripts/production_grants.sql (no-op in dev/test where the role owns the tables).
These triggers are the layer that is always active.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_append_only_delete_guard"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DELETE_FN = "ledger_forbid_delete"
_DELETE_TRG = "trg_transaction_forbid_delete"
_UPDATE_FN = "ledger_guard_update"
_UPDATE_TRG = "trg_transaction_guard_update"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION {_DELETE_FN}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'transaction rows are append-only; DELETE is not permitted'
                USING ERRCODE = 'restrict_violation';
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_DELETE_TRG}
        BEFORE DELETE ON transaction
        FOR EACH ROW EXECUTE FUNCTION {_DELETE_FN}();
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_UPDATE_FN}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT (
                OLD.status = 'ACTIVE'::transaction_status
                AND NEW.status = 'SUPERSEDED'::transaction_status
                AND OLD.superseded_by_id IS NULL
                AND NEW.superseded_by_id IS NOT NULL
                AND NEW.id = OLD.id
                AND NEW.event_type = OLD.event_type
                AND NEW.amount = OLD.amount
                AND NEW.description = OLD.description
                AND NEW.event_date = OLD.event_date
                AND NEW.created_by_id = OLD.created_by_id
                AND NEW.recorded_at = OLD.recorded_at
                AND NEW.created_at = OLD.created_at
                AND NEW.idempotency_key = OLD.idempotency_key
            ) THEN
                RAISE EXCEPTION
                    'transaction rows may only change via the ACTIVE -> SUPERSEDED correction step'
                    USING ERRCODE = 'restrict_violation';
            END IF;

            IF (
                SELECT status FROM transaction WHERE id = NEW.superseded_by_id
            ) IS DISTINCT FROM 'ACTIVE'::transaction_status THEN
                RAISE EXCEPTION
                    'a correction must supersede into an ACTIVE row (forbids forked/cyclic chains)'
                    USING ERRCODE = 'restrict_violation';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_UPDATE_TRG}
        BEFORE UPDATE ON transaction
        FOR EACH ROW EXECUTE FUNCTION {_UPDATE_FN}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_UPDATE_TRG} ON transaction")
    op.execute(f"DROP FUNCTION IF EXISTS {_UPDATE_FN}()")
    op.execute(f"DROP TRIGGER IF EXISTS {_DELETE_TRG} ON transaction")
    op.execute(f"DROP FUNCTION IF EXISTS {_DELETE_FN}()")
