# Closed decisions (curated)

The authoritative detail is in `architecture/`. This is the short list an agent
needs so it doesn't re-open settled points. Build-time implementation choices
are in `docs/decisions/block-1-followups.md`.

## Domain & data

- **Bilateral ledger, two people.** Balance `S`: `S>0` → Erick owes Mamá;
  `S<0` → Mamá owes Erick; `S=0` → `no_debt` (PHASE-2.5 §13 is authoritative;
  the `null` in PHASE-2.9 §4.2 is superseded — see its erratum).
- **Five closed `event_type` values**, concrete names:
  `mama_entrega_dinero` (+), `erick_gasta_para_mama` (−),
  `erick_entrega_dinero` (−), `mama_devuelve` (−), `erick_devuelve` (+).
  The sign lives only in `domain/events.py`; it is never stored and never
  chosen by the LLM or n8n.
- **Append-only.** A correction = new row + old row `SUPERSEDED`
  (`superseded_by_id`), done atomically. Chains `A→B→C`; only the tail is
  `ACTIVE`; the balance sums `ACTIVE` rows only. You may only correct the
  currently `ACTIVE` version. A `BEFORE DELETE` trigger and a transition-only
  `BEFORE UPDATE` trigger enforce this in the DB (migration `0002`).
- **Each person corrects only their own rows** — enforced in the API
  (`CORRECTION_NOT_ALLOWED`, 403), not just the n8n picker.
- **Money:** `Decimal` / `NUMERIC(12,2)`, PEN only, positive, ≤ 2 decimals,
  never `float`. The parser rejects signed amounts and foreign currency
  (foreign currency is terminal — no LLM fallback).
- **Idempotency:** every write carries an `idempotency_key` with a DB `UNIQUE`
  constraint; the API resolves a replay *before* running the parser/LLM.
- `recorded_at` is the registration-timestamp column name.

## Architecture

- **Telegram presents; n8n orchestrates; Python decides; PostgreSQL persists.**
  n8n never computes the balance or a sign and never writes the ledger.
- **FastAPI**, private, never internet-exposed. `X-API-Key` service token
  (`API_INTERNAL_TOKEN`), never the DB password. Endpoints under `/api/v1`:
  `health`, `POST` + `GET /transactions`, `POST /transactions/{id}/corrections`,
  `GET /balance`. Errors: `{"error":{"code","message"}}` with stable codes.
- **SQLAlchemy + Alembic.** Migrations are a deliberate step (compose `migrate`
  service / CI), never auto-run by the container entrypoint. Destructive
  migrations need human approval.
- **PostgreSQL** in dev and prod (never SQLite). Dedicated DB + least-privilege
  role (no `SUPERUSER` / `CREATEDB` / `CREATEROLE`), never publicly exposed.
- **LLM = fallback only**, contract-only in v1 (no provider wired). It may
  return only `{amount, description}`; any other key is rejected.
- **Conversational state** lives in n8n / `gonex-redis` (keys
  `mlbot:conv:<chat_id>`, TTL 30 min), never in our financial DB.
- **Docker:** non-root image; `ledger-api` joins a dedicated `ledger-net` with
  n8n, not all of `docker_gonex-network`.

## Security & data handling

- No secrets, no real financial data, no real Telegram ids in Git. Public repo;
  tests use synthetic data only.
- Backups contain real financial data → treated as sensitive.

## Process

- Human authority (Erick's explicit approval): `git push` / merge, production
  changes, destructive operations, secret changes, architecture changes.
- Per implementation block: Claude Code implements → Codex reviews → fixes →
  close.
