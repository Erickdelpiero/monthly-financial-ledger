# Block 1 — deferred follow-ups

Items surfaced by the first cross-review cycle (Claude Code implementation +
Codex audit) that are **intentionally not enforced in Block 1** because they
need Block 2 (the correction service) and/or production role provisioning.
They are recorded here so they are not lost, per PHASE-2.12 §7.

Block 1 scope is *structure only* (PHASE-2.12 §4): SQLAlchemy models + initial
Alembic migration + persistence tests. No `signed_effect`, balance, or
correction-apply logic.

---

## Addressed in Block 1 (in response to the review)

| Change | Why |
|---|---|
| `UNIQUE(transaction.superseded_by_id)` added | Prevents a **forked** correction chain (`A → C` and `B → C`). Enforces "una única cadena lineal por transacción lógica" (PHASE-2.5 §14.2). NULLs are distinct in PostgreSQL, so ACTIVE rows are unaffected. |
| Tests: fork rejection, NUMERIC rounding behaviour, sub-cent rejection | Make the known behaviours explicit and regression-proof. |

---

## F1 — Cycle prevention in the correction chain  *(CLOSED in Block 2)*

`UNIQUE(superseded_by_id)` + `no_self_supersede` + `status_supersede_consistency`
allowed a 2-cycle via **direct DML**: `A.superseded_by = B` and
`B.superseded_by = A`, both `SUPERSEDED`. Result: no ACTIVE row for that logical
chain → it drops out of `WHERE status = ACTIVE` and out of the balance.

**Closed by the `BEFORE UPDATE` trigger in migration 0002** (see F2). Its
`superseded_by_id` must reference a **currently ACTIVE** row. A cycle can only be
formed by closing an edge onto a node that is already `SUPERSEDED`, which the
trigger rejects — so forked *and* cyclic chains are now impossible for any
writer, including direct DML by the app role. `apply_correction` is additionally
provably acyclic (it points the target at a row inserted moments earlier).

Covered by `tests/test_append_only_guard.py::test_cannot_supersede_into_a_non_active_successor`.

Refs: PHASE-2.6 §11, PHASE-2.5 §14.

## F2 — Append-only enforcement against direct UPDATE / DELETE  *(Block 2 + provisioning)*

Any role with plain DML can today edit `event_type` / `amount` / `event_date` /
`status` of an ACTIVE row, or `DELETE` a row with no inbound FK. That contradicts
"Historical financial events must not be silently overwritten" (PHASE-2.3 §4.4,
§9) and "no elimina físicamente el evento original" (PHASE-2.6 §10).

Block 1 models the append-only *shape* (SUPERSEDED status, `superseded_by`,
consistency checks) but does not lock down who may mutate rows. Block 2 must
make the atomic correction the **only** write path that changes an existing row.

**DECIDED (Erick, cycle 1) — defence in depth, delivered with the Block 2
correction service (Alembic migration + role provisioning), not in Block 1:**

1. **Column-scoped grants** on the production role: `SELECT, INSERT`,
   `UPDATE (status, superseded_by_id)` only — **no `DELETE`**, no `UPDATE` on
   any other column (PHASE-2.6 §4, PHASE-2.7 §8). The app role still needs
   `UPDATE` for the correction flow, so grants cannot be `SELECT, INSERT` only.
2. **`BEFORE DELETE` trigger** on `transaction` that always raises — the
   application never deletes ledger rows in any block.

**Status after Block 2 — CLOSED (both layers now implemented):**

1. **`BEFORE DELETE` trigger** `trg_transaction_forbid_delete` — always raises.
2. **`BEFORE UPDATE` trigger** `trg_transaction_guard_update` — permits **only**
   the `ACTIVE → SUPERSEDED` transition (status + `superseded_by_id`, every
   other column byte-identical, successor row ACTIVE). So even with the granted
   `UPDATE (status, superseded_by_id)` a compromised/buggy runtime cannot
   un-supersede a row, mutate an immutable column, or fork/cycle a chain.
3. **Column-scoped grants** — `scripts/production_grants.sql`: `person` →
   `SELECT` only; `transaction` → `SELECT, INSERT` + `UPDATE (status,
   superseded_by_id)`; no `DELETE`. Applied at provisioning (no-op in dev/test
   where the role owns the tables).

Both triggers ship in migration `0002_append_only_delete_guard` and are active
in every environment. Covered by `tests/test_append_only_guard.py`.

Refs: PHASE-2.3 §14 / §255, PHASE-2.6 §203 / §29, PHASE-2.7 §8.

## F3 — Bilateral (2-person) scope and inactive-user authorization  *(by design: Python + provisioning, not schema)*

The schema allows N `Person` rows and does not stop an `is_active = false`
person from being `created_by`. This is **intentional**: identity is stored as
data, "no se codificará dentro de la lógica financiera" (PHASE-2.3 §7.1), and
authorization lives in Python + controlled configuration (PHASE-2.11 §4.1,
PHASE-2.5 §7).

Guarantees that must exist before/with Block 4 (API / identity resolution):

- Provisioning seeds **exactly two** `Person` rows (Erick, Mamá).
- Python resolves `telegram_user_id → person_id` and **rejects** unknown or
  inactive users without creating any row (PHASE-2.6 §12, PHASE-2.9 §10, §19).
- The five `event_type` values semantically encode exactly these two people;
  adding a third person is a deliberate future redesign of the balance
  semantics, not an incremental change (PHASE-2.3 §2, §25).

No schema constraint is added, because a hard 2-row limit would contradict the
"identity as data" decision and the documented future-extension path.

## F4 — Amount "representable in cents"  *(Block 2 — Python validation)*

`NUMERIC(12,2)` **rounds** on store (`35.999 → 36.00`), it does not reject.
PHASE-2.3 §18 explicitly lists "amount representable con céntimos" among the
**pre-insert Python validations**.

**DECIDED (Erick, cycle 1) — keep `NUMERIC(12,2)`; no schema change:**

- Real amounts always have at most two decimals (Yape / Plin / bank transfers
  in PEN are always `entero` or `entero.cc`), so `NUMERIC(12,2)` is the correct
  storage type and its rounding is never expected to fire on real input.
- Block 2's validation layer still rejects any incoming `Decimal` whose
  exponent is smaller than -2 **before** it reaches the database, so a
  malformed amount is refused rather than silently rounded.

**Status after Block 2:** `money_ledger.domain.money.validate_amount` /
`normalize_amount` (a finite positive `Decimal`, exactly cent-representable,
within NUMERIC(12,2) range; floats rejected) — called by both
`record_transaction` and `apply_correction`. Covered by
`tests/test_record_transaction.py::test_invalid_amounts_are_rejected` and the
Block 1 rounding tests.

---

## Block 2 — decisions resolved in review (cycle 2)

### N1 — `event_date` may not be in the future — **APPROVED (Codex + Erick)**

`record_transaction` / `apply_correction` reject an `event_date` after "today"
in `America/Lima`. No lower bound (PHASE-2.3 §14: old events may be
recorded/corrected). Consistent with "fecha en que ocurrió".

### N2 — `Direction.NO_DEBT` vs `null` — **RESOLVED: `no_debt` is authoritative**

`compute_balance` returns `Direction.NO_DEBT` when `S = 0`, per the enum in
PHASE-2.5 §13, and the API contract keeps `no_debt` (no silent projection to
`null`). PHASE-2.9 §4.2 said `direction = null`; an erratum note has been added
there pointing to PHASE-2.5 §13 as authoritative.

### N3 — service boundary — **APPROVED (Codex + Erick)**

`record_transaction` / `apply_correction` keep the `Person` existence + active
check (`UNKNOWN_PERSON` / `INACTIVE_PERSON`): the write path must stay protected
even if invoked outside HTTP. Block 4 still owns `telegram_user_id → person_id`
resolution and the `UNKNOWN_TELEGRAM_USER` mapping.

### C2-1 — correction idempotency compares the resolved payload

`apply_correction` now returns a stored correction only when the resolved
payload (`created_by_id`, `event_type`, `amount`, `description`, `event_date`)
is identical and it superseded the same `target_id`; otherwise
`DuplicateIdempotencyKey`. Same semantics as `record_transaction`.

### C2-2 — concurrent correction idempotency is deterministic

The idempotency key is re-checked after the target row lock is acquired and
again on a unique-key conflict, so a concurrent retry with the same key returns
the already-created correction instead of `TransactionNotActive`. Covered by
`tests/test_apply_correction.py::test_concurrent_same_key_correction_is_deterministic`
(two real threads/sessions).

### C2-3 — a correction is attributed to the actor, not the original registrant

`apply_correction` takes a required `created_by_id` = the person performing the
correction, validated active, and written to the new row. (Authorization for
who *may* correct whose row remains Block 4 / n8n, per PHASE-2.10 §29.9.)

---

## Block 3 — parser + LLM fallback contract (implementation choices)

### B3-1 — deterministic parser grammar (v1)

`money_ledger.parsing.parse_raw_text` (PHASE-2.5 §9.2):

- **PEN only, terminal.** `S/`, `S/.`, `soles`, `PEN` are stripped; any
  foreign-currency marker (`$`, `USD`, `€`, `dólares`, `euros`, ...) raises
  `UnsupportedCurrency` (a `ParserFailed` subclass) and the resolver **never**
  falls back to the LLM for it — a USD text can't become a PEN movement.
- **Exactly one** number token of **1-10 integer digits** (the NUMERIC(12,2)
  integer range) + optional `.`/`,` and 1-2 decimals. More than one → fail;
  **digit-grouping separators are not supported** (`1.500,50` fails via the
  "leftover digits in the description" check). Real inputs (`S/ 35.50 taxi`)
  pass; anything ambiguous goes to the LLM fallback rather than being guessed.
- **A sign directly before the amount** (`-35.50`, `+35.50`, `- 35.50`,
  U+2212) → `ParserFailed`. The parser never reinterprets a sign; direction is
  set by the event-type button. (Recoverable: the LLM fallback still runs, and
  the n8n confirmation step is the final check.)
- **`0` is extracted, not rejected here**, so `record_transaction` returns the
  precise `INVALID_AMOUNT`. `ParseResult` is documented as *non-negative*, not
  positive — positivity/range are enforced downstream.
- `ParseResult.source` (`deterministic` / `llm`) is recorded so the pilot can
  measure how often the fallback is actually needed (Phase 1 §7).

### B3-2 — no `confidence_score`

Per PHASE-2.9 §8.3, no numeric confidence rule is invented. Safety rests on the
grammar, the output schema, the money validation in `record_transaction`, and
the explicit user confirmation step in n8n.

### B3-3 — LLM fallback is contract-only

No provider is wired (PHASE-2.12 §4). `NullLLMExtractor` is the v1 default and
always raises `LLMFallbackError`. `validate_llm_extraction` enforces an
allow-list: the result may contain **only** `amount` + `description`; any of
`event_type`, `signed_effect`, `signed_amount`, `balance`, `direction`,
`person_id`, `telegram_user_id`, `status`, `payer`, `receiver` (or any other
key) → `LLMFallbackError`. The `amount` must be a **decimal string** (per
PHASE-2.5 §9.3/§10 — a `float` or `Decimal` in the payload is rejected) and is
run through the domain's `normalize_amount` (finite, positive, cent-scale,
within NUMERIC(12,2)). `record_transaction` still re-validates as defence in
depth.

### B3-4 — boundary

Block 3 exposes `resolve_amount_and_description(raw_text, *, llm=None)`. Block 4
(API) will call it with `raw_text` and then hand the structured
`amount` + `description` to `record_transaction` / `apply_correction`. The
services keep accepting structured input directly (PHASE-2.5 §8.2).

---

## Block 4 — FastAPI internal API (implementation choices)

`src/money_ledger/api/` — endpoints `GET /api/v1/health`,
`POST /api/v1/transactions`, `POST /api/v1/transactions/{id}/corrections`,
`GET /api/v1/balance` (PHASE-2.5 §5). Report endpoints are Block 7.

### B4-1 — status codes

- `POST /transactions` and `.../corrections` return **200** for both a new row
  and an idempotent replay (the operations are idempotent; n8n keys off
  `error.code` and the body, not 200 vs 201).
- Error → HTTP: `UNAUTHORIZED` 401 · `UNKNOWN_TELEGRAM_USER` 403 ·
  `TRANSACTION_NOT_FOUND` 404 · `TRANSACTION_NOT_ACTIVE` /
  `DUPLICATE_IDEMPOTENCY_KEY` 409 · `INVALID_*` / `PARSER_FAILED` /
  `LLM_FALLBACK_ERROR` / `VALIDATION_ERROR` 422 · `INTERNAL_ERROR` 500.
  Body is always `{"error": {"code", "message"}}` (PHASE-2.5 §17).

### B4-2 — request typing

Domain-shaped fields (`event_type`, `event_date`, `amount`) are typed as
strings in the Pydantic model and parsed in the route, so a bad value yields a
**specific** code (`INVALID_EVENT_TYPE`, `INVALID_EVENT_DATE`,
`INVALID_AMOUNT`). `model_config = extra="forbid"` rejects any field n8n must
not send — `balance`, `signed_effect`, `signed_amount`, `person_id`, ... →
`VALIDATION_ERROR` (PHASE-2.5 §23, PHASE-2.9 §9.1). The service-token check
runs before body validation (401 wins over 422).

### B4-3 — unknown / inactive Telegram user

`resolve_person` raises `UnknownTelegramUser` (`UNKNOWN_TELEGRAM_USER`, 403) for
**both** "not registered" and "registered but inactive" — aligned with
PHASE-2.5 §17's code list and PHASE-2.11 §4.1 ("unknown → rejected, no row
created"). n8n never sends a `person_id`.

### B4-4 — `/health`

No auth. Runs `SELECT 1`; returns `200 {"status":"ok"}` or
`503 {"status":"unavailable"}`. No version or other detail in the body
(PHASE-2.5 §18).

### B4-5 — `/balance`

API-key protected only; no `telegram_user_id` parameter — the bilateral balance
is shared between the two people (PHASE-2.8 §3). "Authorized user" in
PHASE-2.9 §9.2 is read as the service-token check.

### B4-6 — LLM injection point

`app.state.llm` is `None` in v1, so an unparseable `raw_text` yields
`PARSER_FAILED` (not `LLM_FALLBACK_ERROR`). A real provider is injected via
`create_app(llm=...)` when Block-3's contract gets an implementation.

### B4-7 — session lifecycle & dependency versions

The `get_session` dependency commits once the handler returns cleanly (services
still only `flush`), rolls back on any exception. `fastapi` is pinned to the
`0.115.x` line and `httpx < 0.28` because `starlette 1.x` + `httpx 0.28` emit a
`TestClient` deprecation warning that the suite's warnings-as-errors rejects.

---

## Block 4 — resolved in review (cycle 2)

### C4-1 — idempotency short-circuits BEFORE the parser / LLM (PHASE-2.9 §6.3)

`api/idempotency.py`: after auth + identity, `POST /transactions` and
`.../corrections` look up the `idempotency_key` and decide from **cheap fields
only** (`created_by_id` + `event_type` + `event_date` for a transaction; "is the
successor of the target" for a correction):

- key unused → parse + record normally;
- key used, cheap fields match → return the stored row (**no parse, no LLM
  call**) — a retry whose `raw_text` was mangled in transit still replays;
- key used, cheap fields differ → `DUPLICATE_IDEMPOTENCY_KEY` (still no parse).

`record_transaction` / `apply_correction` keep their own key check as the
race backstop. Test: `test_idempotent_replay_does_not_invoke_the_llm`.

### C4-2 — partial corrections

`CorrectionCreate` requires **at least one** corrigible field (`event_type`,
`event_date`, `raw_text`, `amount`, `description`) → empty body is
`VALIDATION_ERROR`. With no `raw_text`, `amount` and `description` are passed to
`apply_correction` **independently** (each `None` keeps the target's value), so
amount-only and description-only corrections work. Tests:
`test_correct_only_amount_keeps_description`,
`test_correct_only_description_keeps_amount`, `test_empty_correction_body_is_422`.

### C4-3 — raw_text XOR structured

Both `TransactionCreate` and `CorrectionCreate` reject a request that carries
`raw_text` **and** `amount`/`description` → `VALIDATION_ERROR`. The structured
path stays available for tests / controlled integration but can no longer
silently override the text.

### C4-4 — parser safety, at the API layer

The Block-3-review fixes (reject signed amounts; foreign currency is a terminal
`UnsupportedCurrency` that never reaches the LLM) are now covered by API tests:
`test_signed_amount_in_raw_text_is_422_parser_failed`,
`test_negative_structured_amount_is_422_invalid_amount`,
`test_foreign_currency_never_reaches_the_llm` (asserts `llm.calls == []`).

### C4-5 — correction attribution test

`test_correction_is_attributed_to_the_actor` now asserts the returned
`created_by` equals Mamá's exact person UUID (and differs from Erick's).

---

## Block 5 — Docker image + local compose (implementation choices)

### B5-1 — split requirements

`requirements.txt` is now **runtime only**; `pytest` / `httpx` move to
`requirements-dev.txt` (`-r requirements.txt` + tools). Still the
`requirements.txt` workflow, not a tooling change — the split keeps a test
framework out of the runtime image (PHASE-2.9 §14.1). Local dev / CI installs
`requirements-dev.txt`; the Dockerfile installs `requirements.txt`.

### B5-2 — Dockerfile

Multi-stage (`python:3.11-slim-bookworm`): a builder stage installs deps into
`/opt/venv`, the runtime stage copies only the venv + `src/` + `migrations/` +
`alembic.ini`. Runs as a dedicated **non-root** user `app` (uid 10001,
PHASE-2.9 §14.2). `HEALTHCHECK` hits `/api/v1/health` with stdlib `urllib` (no
`curl` in the image). No secrets baked in — configuration is entirely from the
environment (PHASE-2.7 §12). `CMD` runs `uvicorn --factory
money_ledger.api.app:create_app`; worker tuning is deferred (PHASE-2.7 §15).

### B5-3 — migrations are a deliberate step, not an entrypoint side effect

The container does **not** auto-run `alembic upgrade head` (PHASE-2.7 §17 — the
deploy path must not silently apply a destructive migration). Locally, a
one-shot `migrate` compose service runs the upgrade and `api` waits on it
(`service_completed_successfully`). Production runs migrations as an explicit
CI step (Block 8).

### B5-4 — `docker-compose.yml` is local only

`db` (`postgres:16`, matching prod) + `migrate` + `api` on a dedicated bridge
network `ledger-net` — **not** `docker_gonex-network` (PHASE-2.7 §9,
PHASE-2.11 §5). Host ports are bound to `127.0.0.1` only; nothing is exposed to
the internet. `POSTGRES_DB` is `money_ledger` (its own DB, separate from the
host-side `money_ledger_dev` / `money_ledger_test` used by `scripts/local_db_setup.sql`).
The production stack and the `gonex-postgres` wiring are Block 8.

### B5-5 — container verification is pending a Docker-capable environment

`tests/test_docker_image.py` and `tests/test_docker_compose.py` are marked
`@pytest.mark.docker` and **skip** when no Docker daemon is reachable — the case
in the sandbox used so far. See C5-4: running them (or `scripts/docker_smoke.sh`)
where Docker exists is a **hard prerequisite** for Block 8.

---

## Block 5 — resolved in review (cycle 2)

### C5-1 — DB password is never string-interpolated into a URL

`get_database_url()` now: full `DATABASE_URL` if set, **otherwise assembled from
components** (`DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`) via
`sqlalchemy.URL.create(...).render_as_string()`, which percent-encodes the
password. `docker-compose.yml` passes those components (a shared `x-db-env`
anchor), never a hand-built `postgresql://user:${PASSWORD}@...` string. A
password with `@ : / # %` or a space is safe. Covered by
`tests/test_config.py` (round-trip of reserved-char passwords) and, end-to-end,
by `test_docker_compose.py` which runs the stack with `p@ss:w/rd#1%2 x`.

### C5-2 — `docker_smoke.sh` no longer sources `.env`

It never runs `. ./.env`. Compose reads `.env` itself for `${...}` expansion;
the script asks `docker compose port api 8000` for the published address and
uses defaults otherwise. No secret is read by the shell.

### C5-3 — deeper image assertions

`test_docker_image.py` now: `find / -xdev` for `.env` / `conftest.py` /
`pytest.ini` / `test_*.py` / `tests` / `.git` (0 results), `pip list` has no
`pytest` / `httpx`, and `docker inspect` confirms `Config.User == "app"`,
`Config.Cmd` is the exact uvicorn factory command, and a `HEALTHCHECK`
referencing `/api/v1/health` is present.

### C5-4 — operational validation is a hard prerequisite for Block 8

Before the deployment block, **one of** `scripts/docker_smoke.sh` or
`pytest -m docker` MUST be run on a machine with a Docker daemon and must
confirm: image builds, `migrate` reaches `0002` head, `api` becomes `healthy`,
`id -u` ≠ 0, `down -v` cleans up. This is not an "acceptable skip" — it is
pending real verification (no daemon was available in the build sandbox).

`test_docker_compose.py` supplies every required variable through the
subprocess environment, so it does **not** require a `.env` file — a clean CI
checkout with Docker runs it. (`scripts/docker_smoke.sh` still expects `.env`,
which is correct for manual local use.)

---

## Block 6 — n8n + Telegram (in progress; VPS-blocked)

Full design + read-only discovery plan: `docs/block-6-n8n-telegram.md`. The
n8n workflows, the Telegram webhook, and the production Docker network are
**not touched** — they need discovery evidence and a change/rollback plan
first (PHASE-2.12 §6).

### B6-1 — `GET /api/v1/transactions` added (resolves the 2.5 ↔ 2.10 gap)

PHASE-2.10 §18.1's correction picker needs "the user's last 3-5 ACTIVE
transactions"; PHASE-2.5 §5 had no such endpoint. Added:
`GET /api/v1/transactions?telegram_user_id=&status=active|superseded|all&limit=1..20`
— `X-API-Key`, resolves the person, returns **only their** rows, newest
`event_date` first. Read-only projection. `list_recent_transactions` in the
service layer; `tests/test_api_list_transactions.py` (9 tests).

### B6-2 — decisions taken (cycle 2, after discovery + Codex review)

- **D1 — conversational state → `gonex-redis`** (hostname `gonex-redis:6379`,
  reachable from n8n; corrected from the assumed `redis`). Keys
  `mlbot:conv:<chat_id>`, `EX 1800`. Never our financial DB (PHASE-2.4 §5).
- **D3 — dedicated bot `@CuentasDN_bot`** created (token stays in Erick's local
  `.env`, never shared).
- **D4 — "correct only your own rows" is now enforced in the API**, not just
  the picker: `apply_correction` raises `CorrectionNotAllowed`
  (`CORRECTION_NOT_ALLOWED`, 403) when the ACTIVE target's `created_by_id` is
  not the actor (PHASE-2.10 §18.1 / §29.9). Tests added in
  `test_apply_correction.py` and `test_api_corrections.py`.
- **Network**: create a dedicated `ledger-net` for `n8n ↔ ledger-api`; do **not**
  attach the API to all of `docker_gonex-network` (shared with 7 containers —
  PHASE-2.7 §8, PHASE-2.11 §5).
- **Private chats only** (Codex): workflow A/B reject `chat.type != "private"`
  and any sender that is not one of the two authorised ids — the state is keyed
  by `chat_id`, so a shared group chat could clobber state.
- `list_recent_transactions` order gets `id DESC` as a stable third key.

### B6-3 — still open

- Redis auth on `gonex-redis` (runbook step 0).
- Everything in `docs/block-6-n8n-telegram.md` Part 5 (the manual runbook Erick
  executes) — nothing is applied until that + the design are reviewed.

### B6-5 — n8n workflow review (cycle: Codex on the exports)

Fixes to `n8n/workflow-*.json`:

1. **B error path did not revert state** — the user was stuck in
   `PROCESSING_CORRECTION` (which B ignores) until the 30-min TTL expired.
   Added `Redis: revertir (err) B`; `Handle corr` now returns `revertState`
   restoring `WAITING_CORRECTION_CONFIRMATION` with `pending_idempotency_key`,
   mirroring A's `Redis: revertir (err)`.
2. **"md" correction preview showed the OLD amount as final.** When the user
   supplies free text, amount/description are only known after the API parses
   it, so the before/after summary now shows
   `[monto y descripcion a interpretar de: "<texto>"]` instead of the old
   amount.
3. `TG: err B` gained REINTENTAR/CANCELAR buttons (parity with A `TG: error`).
4. **`/corregir` mid-registration** (PHASE-2.10 §20): A no longer silently
   discards an in-progress registration. New `route 4` → *Preguntar pendiente*
   sends "Tienes un registro sin terminar" + *Continuar registro / Cancelar y
   corregir*; `route 3` resolves the answer.
5. Fixed `Handle corr` reading `fromId` from the wrong node (was
   `Correccion SM`, which does not carry it → notifications never fired); now
   `$('Inicio (desde A)').item.json.fromId`.

### B6-6 — fix: Redis `get` node drops the update fields (found on the VPS, Step 8/9)

First real Telegram messages failed in **every** execution at `TG: con botones`
with `Bad Request: chat_id is empty`. Root cause: the n8n Redis **`get`**
node (`Load state` in A, `Cargar estado` in B) returns an item containing
**only** the retrieved property (`stateRaw`); it does **not** carry through the
fields the previous node produced. So `Router` (A) and `Correccion SM` (B),
which did `const j = $input.first().json`, lost `chatId`, `fromId`, `text`,
`callbackData`, `isCallback`, `updateId` and — in A — `blocked`. Effects:
`chatId` undefined everywhere downstream (the visible error); the
private-chat/authorised-sender guard silently bypassed (`blocked` undefined →
`route 0` unreachable); routing collapsed to "always registration";
`telegram_user_id` sent as `"undefined"`; idempotency key
`telegram:undefined:update:undefined`.

Fix (Code nodes only — paired-item access `$('X').item` still works, so no
other node changed):

- A `Router`: read the update fields from `$('Parse update').first().json`,
  keep only `stateRaw` from `$input`, emit `Object.assign({}, p, {route, state})`.
- B `Correccion SM`: rebuild `j` from `$('Inicio (desde A)').first().json`
  (`chatId/fromId/updateId/text/callbackData/isCallback/forceCorrection`), keep
  `stateRaw` from `$input`.

`n8n/README.md` gained a checklist line so a future re-export doesn't
"simplify" these back to `$json`.

### B6-7 — fix: inline keyboards didn't render + n8n attribution footer (VPS, Step 9)

Live "¿Qué ocurrió?" arrived as plain text, no buttons, plus a
" This message was sent automatically with n8n" footer. Two causes:

1. **Keyboard shape.** The `kb()` helper and the hand-built keyboards wrapped
   each button as `{ button: { text, additionalFields } }`. The n8n Telegram
   node reads `inlineKeyboard.rows[].row.buttons[].text` /
   `.additionalFields` **directly** — the extra `button` key made every button
   `text: undefined`, so Telegram dropped the markup. Removed the wrapper in
   `Registro SM` / `Correccion SM` `kb()`, `Preguntar pendiente`,
   `Construir picker`, and the `TG: error` / `TG: err B` literals.
2. **Attribution.** The Telegram `sendMessage` node defaults
   `appendAttribution: true`. Set `additionalFields.appendAttribution = false`
   on all 14 `sendMessage` nodes (not the trigger).

Repo exports fixed. On the VPS the low-risk path is now a **re-import** of both
files followed by re-entering the 3 Step-8 constants + the workflow-B id, since
the alternative is ~20 hand-edits.

**Update:** item 2 (attribution) held; item 1 (keyboard shape) did **not** fix
the missing buttons — superseded by B6-8.

### B6-8 — inline keyboards: native Telegram node can't do dynamic `reply_markup`

Even with the shape corrected, buttons still didn't render. Root cause is a
known limitation of `n8n-nodes-base.telegram`: it does not reliably build an
inline keyboard from an expression (any shape). Confirmed on the n8n community
forum ("Use HTTP node instead. Telegram node doesn't support dynamic
properties" — community.n8n.io/t/…/185655).

**Fix:** the 6 keyboard-sending nodes are now **HTTP Request** nodes calling
`https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage` with a
JSON body (`chat_id`, `text`, `reply_markup`). The `kb()` helper and the two
literal keyboards (`Preguntar pendiente`, `Construir picker`) now emit
Telegram's native `{ inline_keyboard: [[{ text, callback_data }]] }` directly,
so the HTTP body passes `n8nKeyboard` straight through. `TG: error` /
`TG: err B` carry their fixed retry/cancel markup inline in the body.

- **Token:** `TELEGRAM_BOT_TOKEN` env var on the `gonex-n8n` container
  (Erick's choice over a Redis config key: better isolation — `gonex-redis`
  has no auth and is shared with 7 containers). Never in Git or a node.
  n8n credentials can't be referenced from an HTTP Request node's expressions,
  and Telegram only accepts the token in the URL path (not a header/query), so
  a "Header Auth" credential is not an option.
- **The other two constants moved to `$env` too** (Erick, so a re-import keeps
  nothing to re-type): `Parse update` reads `AUTHORIZED_IDS` from
  `TELEGRAM_AUTHORIZED_IDS` (`"id1,id2"` → numbers); `Handle API` / `Handle
  corr` read `OTHER` from `TELEGRAM_OTHER_MAP` (JSON string → `JSON.parse`).
  Both `try/catch` to `[]` / `{}` — fail closed (empty auth list = "Este bot
  es privado"; empty map = no cross-notification). No `TODO (Step 8)` left in
  the exports.
- The native Telegram node is kept for the Trigger and the 8 non-keyboard
  sends (they work fine and reuse the existing `Telegram account-CuentasDN`
  credential).
- Also hardened: `Correccion SM` / `Router` parse guard is now
  `(… ) || {}` (an empty picker used to persist the string `"null"`), and the
  empty-picker branch writes `stateNext: {}` instead of `null`.

Runbook Step 4 gained the env-var step; `n8n/README.md` credential map + the
keyboard checklist item updated.

### B6-4 — fix: DB URL no longer passes through Alembic's configparser

Reported from the VPS: `alembic upgrade head` raised
`ValueError: invalid interpolation syntax` because a random password contained
`%` (and C5-1's `URL.create().render_as_string()` percent-encodes reserved
chars). `migrations/env.py` used `config.set_main_option("sqlalchemy.url", …)`,
which stores the value in Alembic's `ConfigParser` (`BasicInterpolation` treats
`%` as a sigil). Fixed: the URL is passed via `config.attributes["db_url"]` (a
plain dict) or `get_database_url()`, and the online path uses
`create_engine(url, poolclass=NullPool)` directly instead of
`engine_from_config(config.get_section(...))`. `tests/conftest.py` passes the
URL the same way. Regression:
`tests/test_migrations.py::test_upgrade_tolerates_percent_in_the_db_url`.
Confirmed: CLI `alembic upgrade head` with a `%`-laden `DATABASE_URL` reaches
`0002 (head)`.

---

## Block 6 — CLOSE-OUT

### B6-9 — Block 6 closed (2026-09-01); the real blocker was `N8N_BLOCK_ENV_ACCESS_IN_NODE`

**Root cause (not just "resolved").** B6-6/7/8 were real bugs, but none was why
`AUTHORIZED_IDS` / `OTHER` / the bot token kept coming back empty on the VPS.
The blocker was **n8n blocking `$env` in Code nodes by default**:
`N8N_BLOCK_ENV_ACCESS_IN_NODE` defaults to `true` from n8n **2.0** onward. It
had never been set on the `gonex-n8n` service, so every `$env.*` read (in a
Code node *or* an expression) returned `undefined` regardless of how many times
the workflow code was fixed or the workflows re-imported. That is why the
symptom survived every earlier fix.

**Fix (VPS `docker-compose.yml`, n8n service `environment:` block):**

```yaml
    environment:
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

then recreate the container (`docker compose up -d --no-deps <n8n service>`).

**Security trade-off (accepted):** this enables `$env` for **every** workflow
on that n8n instance, not only ours. `gonex-n8n` is shared infra. Anyone who
can edit a workflow there can now read the container's env (which includes the
bot token and any other service's secrets passed as env). Judged acceptable
for a single-operator instance; revisit if more people get n8n editor access.

**Reusable finding (framework, not just this project):** on any n8n ≥ 2.0, a
Code node or expression that reads `$env` needs
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` set **explicitly** on the container — do
not assume the default. And weigh the trade-off above before choosing `$env`
over a per-workflow mechanism (a Set node, a fetched config row, a dedicated
credential) on a shared instance.

**E2E verification — PARTIAL.** Registration happy path confirmed end to end
(Telegram screenshots): inline buttons render, no "sent automatically with n8n"
footer, full flow tipo → monto/descripción → fecha → resumen → CONFIRMAR →
"Registrado", and `erick_gasta_para_mama` `S/ 10.00` →
"Mamá le debe a Erick: S/ 10.00" (sign matches PHASE-2.3). **Deferred to a
later session, non-blocking:** the Nora notification, `GET /api/v1/balance`
via the API, `/corregir` with the before/after summary, Nora not seeing
Erick's row in her picker (+ `403 CORRECTION_NOT_ALLOWED` on a direct call),
and netting the balance back to zero. Once the deferred `S/ 10.00` test row is
netted, note it and its offset here.

**State on close.** Workflows A/B on the VPS (A active, B inactive
sub-workflow); webhook on `@CuentasDN_bot` → n8n; 2 `Person` rows
(`8398733157` Erick, `8471171060` Nora); config as `$env` on `gonex-n8n`
(`TELEGRAM_BOT_TOKEN` / `TELEGRAM_AUTHORIZED_IDS` / `TELEGRAM_OTHER_MAP` +
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`). One `S/ 10.00` real test row in the
ledger, pending offset. Interim `ledger-api` container stays until Block 8.

**Cycle note.** B6-4/6/7/8/9 were found and fixed reactively during the VPS
deploy, outside the normal "Codex reviews" loop. The Python suite is unchanged
by them (the changes are n8n JSON exports + docs); no new pytest run was
required. A Codex pass over `n8n/workflow-*.json` + this entry is the
outstanding review debt if the pilot wants one before Block 7.

### B6-10 — substitute Codex review of `n8n/workflow-*.json` (2 minor fixes)

Codex was unavailable (usage cap to month-end); review done as a substitute
pass. Two non-blocking findings, both fixed in the same commit:

1. **Telegram HTTP sends had no error tolerance.** The 6 HTTP Request nodes
   that call the Telegram API (`TG: con botones`, `TG: error`,
   `TG: preguntar pendiente`; B `TG: botones B`, `TG: picker B`, `TG: err B`)
   lacked `options.response.response = { neverError: true, fullResponse: true }`
   — unlike the ledger-API calls. A Telegram 4xx/5xx would have failed the
   whole execution. Added the option (no retry logic — all 6 are terminal
   nodes, so this just lets the execution end cleanly instead of erroring).

2. **`Construir picker` (B) empty-list case didn't actually DELETE.** It set
   `redisAction: 'del'`, but `Redis: guardar picker` was hard-wired to SET, so
   an empty picker wrote `"{}"` with a TTL instead of removing the key.
   Harmless in practice (`state.step || 'IDLE'` covers it) but inconsistent.
   Fixed to match the `Estado` / `Estado B` pattern: new **`Estado picker`**
   switch on `redisAction` → `Redis: guardar picker` (set) or the new
   **`Redis: borrar picker`** (del); both converge on `TG: picker B`.

Workflow B goes from 23 to 25 nodes. `node --check` clean on all Code nodes;
connections verified. No Python change.

**Block 6 is now fully closed** — implementation + cross review (substitute).

---

## Block 7 — reports (implementation choices)

`src/money_ledger/reports/` — a read-only projection layer over the ledger
(PHASE-2.8, PHASE-2.5 §19-20). Every figure comes from the existing
`get_balance` / ACTIVE-rows path; a report never runs its own calculation
(PHASE-2.8 §3, §15).

Scope confirmed with Erick before implementation (A-E):
A weekly report is a **new endpoint** (Python renders the fixed text);
B monthly "Saldo actual" is the **global** current balance, not month-scoped;
C **matplotlib** for the PNG; D **v1 minimum** — table shows only the ACTIVE
version, no correction markers; E n8n scheduler workflows are **not** in
Block 7 (they go with Block 8).

### B7-1 — three endpoints (PHASE-2.5 §5)

- `GET /api/v1/reports/weekly` → `{"text": <fixed template>, "balance": {...}}`.
  `X-API-Key`, no `telegram_user_id` (bilateral balance is shared, PHASE-2.8 §2,
  matches `/balance`). Text is `📊 Saldo actual\n\n<debt line>` per PHASE-2.8 §4.
- `GET /api/v1/reports/monthly?year=&month=` → JSON: `year`, `month`, `period`
  ("Agosto 2026"), `balance` (global), `movements[]`
  (`event_date`, `recorded_at`, `person`, `event_type`, `movement`, `amount`,
  `description`). No `idempotency_key` / internal ids (PHASE-2.8 §5.3).
- `GET /api/v1/reports/monthly/image?year=&month=` → `image/png` bytes.

`year`/`month` are `Query(ge=2000, le=2100)` / `Query(ge=1, le=12)` → a bad or
missing value is FastAPI's `VALIDATION_ERROR` 422, the same pattern as
`limit` on `GET /transactions` (no bespoke `INVALID_REPORT_PERIOD` code — kept
consistent with the codebase; `monthly_report()` also guards the range when
called directly, per the N3 "services validate even off-HTTP" decision).

### B7-2 — implementation notes

- **Month filter is on `event_date`**, not the registration timestamp: the
  monthly report audits a period of real events, so a movement registered late
  still lands in the month it occurred (PHASE-2.8 §5).
- **Movement labels** (`reports/labels.py`) reuse the exact strings from the
  Telegram buttons (`n8n/workflow-a-registro.json` `LABELS`) so the report is
  worded like the bot. `assert` covers every `EventType`.
- **`_LIMA` timezone** for the "Hora" column: `recorded_at` (stored tz-aware)
  is converted to `America/Lima` and shown `HH:MM`.
- **matplotlib** added to `requirements.txt` (runtime — the PNG is a runtime
  feature). Agg backend, no display server. It is imported **lazily inside the
  image route handler** so the other seven endpoints and app startup don't pay
  the import cost. Note: the Docker image grows (~matplotlib + numpy + pillow)
  and builds a font cache on first PNG in production (one-off).
- **PNG layout** is intentionally plain (header block + table that grows
  downward; long descriptions clipped with `…`); PHASE-2.8 §16 leaves the
  visual design to implementation.

### B7-3 — tests

- `tests/test_reports_service.py` — weekly text for all three directions;
  monthly filtering by `event_date` month, chronological order, only-ACTIVE
  (a corrected row shows the correction), row fields, global (not month-scoped)
  balance, empty month, invalid period raises.
- `tests/test_reports_render.py` — `render_monthly_png` emits real PNG bytes
  for the empty and populated cases and tolerates a naive `recorded_at`
  (no pixel comparison — visuals are implementation-defined).
- `tests/test_api_reports.py` — all three endpoints: shapes, `X-API-Key` 401,
  `year`/`month` 422 (missing / 0 / 13 / 99), empty month, `image/png`
  content-type + PNG magic bytes.

**Suite:** `276 passed` (6 docker-marked deselected), run twice under
`-W error` against a real local PostgreSQL. `pgserver` was used for the
ephemeral DB and removed afterwards; `matplotlib` stays (it is now a runtime
dependency).

**Cycle:** Codex still unavailable (usage cap). A substitute review of the
Block 7 diff is the outstanding review debt, same as B6-10.
