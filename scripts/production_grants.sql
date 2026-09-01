-- F2 (docs/decisions/block-1-followups.md) -- PRODUCTION ONLY.
--
-- Apply after `alembic upgrade head`, connected to the production database as
-- the role that OWNS the schema (NOT the application role). In dev/test the
-- application role owns the tables, so column-level grants do not apply there
-- and this script is unnecessary -- the BEFORE DELETE / BEFORE UPDATE triggers
-- from migration 0002 are the layer that is always active.
--
-- Least privilege for the runtime app role (PHASE-2.6 §4, PHASE-2.7 §8,
-- PHASE-2.11 §4.1):
--   * person       -> SELECT only. The two authorised people are created by
--                     provisioning/admin; the runtime never inserts people.
--   * transaction  -> SELECT + INSERT, plus UPDATE on exactly the two columns
--                     the correction step writes. No DELETE.
--
-- Replace :app_role with the real least-privilege role name before running,
-- e.g.  psql -v app_role=money_ledger_app -f scripts/production_grants.sql

REVOKE ALL ON person      FROM :app_role;
REVOKE ALL ON transaction FROM :app_role;

GRANT SELECT ON person TO :app_role;

GRANT SELECT, INSERT ON transaction TO :app_role;
GRANT UPDATE (status, superseded_by_id) ON transaction TO :app_role;

-- Deliberately NOT granted: INSERT/UPDATE/DELETE on person; DELETE on
-- transaction; UPDATE on any other transaction column. The BEFORE UPDATE
-- trigger additionally restricts even the granted UPDATE to a single
-- ACTIVE -> SUPERSEDED transition, so a compromised or buggy runtime cannot
-- un-supersede a row, mutate an immutable column, or build a forked/cyclic
-- correction chain by direct DML.
