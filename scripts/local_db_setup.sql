-- Local development / test bootstrap for Block 1.
--
-- Run ONCE as a PostgreSQL superuser (e.g. the `postgres` role) against your
-- LOCAL PostgreSQL 16 instance. NEVER run this against production.
--
-- Creates:
--   * money_ledger_app   : dedicated LOGIN role, least privilege
--                          (NO SUPERUSER / NO CREATEDB / NO CREATEROLE)
--   * money_ledger_dev   : dev database,  owned by money_ledger_app
--   * money_ledger_test  : test database, owned by money_ledger_app
--
-- Rationale: architecture PHASE-2.1 §7, PHASE-2.6 §3-4, PHASE-2.11 §4.4.
-- The app role owns its own databases, so it can run its own Alembic
-- migrations locally without ever needing instance-wide privileges.
--
-- Change the password below before running; keep the real value only in your
-- local .env (never committed).

CREATE ROLE money_ledger_app WITH
    LOGIN
    PASSWORD 'change-me-locally'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

CREATE DATABASE money_ledger_dev  OWNER money_ledger_app;
CREATE DATABASE money_ledger_test OWNER money_ledger_app;

-- Optional hardening: keep other roles out of the public schema of each DB.
-- Run these connected to each database (\c money_ledger_dev / \c money_ledger_test):
--   REVOKE ALL ON SCHEMA public FROM PUBLIC;
--   GRANT ALL ON SCHEMA public TO money_ledger_app;
