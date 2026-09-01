# Personal Expense Ledger — Bot

A small personal Telegram bot that keeps a **bilateral money-flow ledger**
between two people. Deterministic financial logic in Python; PostgreSQL is the
source of truth; n8n orchestrates; Telegram is the interface.

Full design: [`architecture/`](architecture/) (Phase 1 + Phase 2.1–2.12, closed
and approved). Implementation follows the block order in `PHASE-2.12` §4.

---

## Implemented so far

**Block 1 — Data model + Alembic migrations** (structure only)

- `src/money_ledger/models/` — `Person` and `Transaction` SQLAlchemy 2.0 models,
  closed `EventType` / `TransactionStatus` enums.
- `migrations/versions/0001_initial_schema.py` — hand-written initial migration.
- persistence tests: integrity, idempotency (`UNIQUE`), correction *structure*,
  migration up/down/round-trip, least-privilege DB role.

**Block 2 — Pure financial rules + ledger services**

- `src/money_ledger/domain/` — `signed_effect` (the single source of truth for
  the sign), `compute_balance` / `Direction`, money validation (`validate_amount`
  / `normalize_amount`, F4), typed domain errors.
- `src/money_ledger/services/ledger_service.py` — `record_transaction`,
  `apply_correction` (atomic; takes the correcting actor's `created_by_id`;
  payload-aware idempotency that also holds under concurrent retries; rejects
  correcting a SUPERSEDED row), `get_balance`. These run inside the caller's
  transaction and never `commit`.
- `migrations/versions/0002_append_only_delete_guard.py` — `BEFORE DELETE` and
  `BEFORE UPDATE` triggers: a ledger row can only ever change via the
  `ACTIVE → SUPERSEDED` correction step (this also makes forked/cyclic chains
  impossible). `scripts/production_grants.sql` is the column-scoped-grants half.
- tests: `test_signed_effect`, `test_balance`, `test_record_transaction`,
  `test_apply_correction`, `test_append_only_guard`.

**Block 3 — Deterministic parser + LLM fallback contract**

- `src/money_ledger/parsing/` — `parse_raw_text` (PEN-only and terminal on a
  foreign currency; one-number grammar; rejects signed amounts; ambiguous input
  fails rather than guesses), the `LLMExtractor` contract with `NullLLMExtractor`
  (v1 default) and `validate_llm_extraction` (allow-list: the LLM may only
  return `amount` + `description`, as a decimal string, revalidated through the
  domain money rules), and `resolve_amount_and_description` (deterministic
  first, LLM only as fallback, never for a foreign currency). No real LLM
  provider is wired. No `confidence_score` (PHASE-2.9 §8.3).
- tests: `test_parse_deterministic`, `test_llm_contract`, `test_resolve`
  (pure Python, no database).

**Block 4 — FastAPI internal API**

- `src/money_ledger/api/` — a private FastAPI app (`create_app`, run with
  `uvicorn --factory money_ledger.api.app:create_app`), never exposed to the
  internet. Endpoints: `GET /api/v1/health`, `POST /api/v1/transactions`,
  `GET /api/v1/transactions` (recent rows, for the correction picker),
  `POST /api/v1/transactions/{id}/corrections`, `GET /api/v1/balance`.
- `X-API-Key` service-token auth (`API_INTERNAL_TOKEN`); `telegram_user_id →
  person_id` resolution rejecting unknown/inactive users; structured
  `{"error": {"code", "message"}}` responses with stable codes; `extra="forbid"`
  so n8n cannot send `balance` / `signed_effect` / `person_id`.
- Idempotency is checked before the parser/LLM runs (a replay never re-parses);
  `raw_text` and structured `amount`/`description` are mutually exclusive.
- tests: `test_api_health`, `test_api_auth`, `test_api_transactions`,
  `test_api_corrections` (real app over the test database).

**Block 5 — Docker image + local compose**

- `Dockerfile` — multi-stage, `python:3.11-slim`, runs as a **non-root** user,
  `HEALTHCHECK` on `/api/v1/health`, no secrets baked in.
- `docker-compose.yml` — local stack: `db` (`postgres:16`) → `migrate`
  (one-shot `alembic upgrade head`) → `api`, on a private bridge network, host
  ports bound to loopback only.
- `docker compose up --build` (needs `.env` from `.env.example`).
- tests: `test_docker_image.py` (`@pytest.mark.docker`, skipped without a
  daemon); full-stack check via `scripts/docker_smoke.sh`.

**Not yet** (Block 6+): n8n/Telegram integration, the monthly report endpoints
+ rendering, CI/CD + deployment (incl. the `gonex-postgres` production wiring).
Open review items and cross-doc inconsistencies are tracked in
[`docs/decisions/block-1-followups.md`](docs/decisions/block-1-followups.md).

Confirmed naming decisions: event types use concrete names
(`mama_entrega_dinero`, `erick_gasta_para_mama`, `erick_entrega_dinero`,
`mama_devuelve`, `erick_devuelve`); the registration timestamp column is
`recorded_at`.

---

## Quick start (Docker)

```bash
cp .env.example .env        # set POSTGRES_PASSWORD and API_INTERNAL_TOKEN
docker compose up --build   # db -> migrate -> api on http://127.0.0.1:8000
```

## Prerequisites (host-side development)

- Python 3.11+
- A **local** PostgreSQL 16 server (or use the compose `db` service). Options:
  - native: `sudo apt install postgresql-16`
  - `docker compose up -d db`
  - an existing local instance

Never point this project at the production database (`architecture/PHASE-2.6` §16).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest/httpx

cp .env.example .env        # then edit .env with your local connection strings
```

Create the dedicated least-privilege role and the two databases (run as a
Postgres superuser, against your LOCAL instance):

```bash
psql -h localhost -U postgres -f scripts/local_db_setup.sql
```

Edit the password in `scripts/local_db_setup.sql` first, and put the same value
in `.env` (never commit `.env`).

## Apply the migration (dev database)

```bash
alembic upgrade head        # reads DATABASE_URL from .env
```

## Run the tests

The suite runs against a **real** disposable PostgreSQL database named by
`TEST_DATABASE_URL`. It builds the schema by running the Alembic migration, and
skips entirely if `TEST_DATABASE_URL` is unset.

```bash
pytest
```

If `test_role_privileges.py` fails, you're connecting as a superuser — use the
`money_ledger_app` role from `scripts/local_db_setup.sql`.
