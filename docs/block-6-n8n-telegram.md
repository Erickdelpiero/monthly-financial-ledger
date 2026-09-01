# Block 6 — n8n + Telegram integration

**Status:** design finalized. The API-side policy fix (D4) is implemented and
tested. **Nothing on the VPS / n8n / the Telegram webhook has been changed** by
an agent — the manual runbook in Part 5 is for Erick to execute.

Reference: PHASE-2.10 (Telegram ↔ n8n UX & conversational flow), PHASE-2.4 §5
(n8n owns conversational state), PHASE-2.5 (API contract).

---

## Part 1 — Discovery evidence (recorded)

| Item | Result |
|---|---|
| n8n container / network | `gonex-n8n`, on `docker_gonex-network` **shared with 7 containers** (evolution, tb-web-report, mosquitto, postgres, thingsboard, n8n, redis). Not a dedicated network. |
| n8n version | `n8nio/n8n:latest` → **2.12.3** |
| Redis | reachable from `gonex-n8n` at hostname **`gonex-redis`** (not `redis`), port `6379`, confirmed with `nc`. Auth status not yet checked (runbook step 0). |
| Telegram bot | **`@CuentasDN_bot`** created via BotFather. Token stored only in Erick's local `.env` — never shared with an agent. |
| Current webhook | clean: no URL configured, `pending_update_count = 0`. |

**Read-only vs. change:** creating the bot was an *approved change*, not
discovery — it is logged in the change/rollback table (Part 6), not Part 1.

---

## Part 2 — Design decisions

### D1 — conversational state store → **`gonex-redis`, namespaced + TTL**

- Keys: `mlbot:conv:<chat_id>` (JSON value). Never `redis`-bare, never our
  financial DB (PHASE-2.4 §5).
- Every turn: read → mutate → write with `EX 1800` (30 min). On
  `COMPLETED` / `CANCELLED` / `CORRECTION_COMPLETED` / `CORRECTION_CANCELLED`:
  `DEL`. The 30-minute inactivity timeout (PHASE-2.10 §19) is just the key TTL
  expiring — no separate timer. `PROCESSING` states resolve in seconds, well
  inside the TTL, so they never expire mid-call.
- n8n 2.12 has a native **Redis** node; use it with a Redis credential.
- Rationale over n8n static data: real TTL, survives workflow edits, not one
  growing JSON blob. `gonex-redis` is shared infra but the footprint is a
  handful of tiny, self-expiring keys under our own prefix.

### D2 — `GET /api/v1/transactions` (implemented in cycle 1)

`?telegram_user_id=&status=active|superseded|all&limit=1..20` (default 5).
`X-API-Key`; resolves the person; returns **only that person's** rows, ordered
`event_date DESC, recorded_at DESC, id DESC` (stable). Read-only projection.

### D3 — **dedicated bot `@CuentasDN_bot`** (done)

Independent token / webhook / command set.

### D4 — "each person corrects only their own entries" → **enforced in the API**

PHASE-2.10 §18.1 / §29.9 default is *no cross-correction*. This is now a
**server-side rule**, not just a picker convention:

- `apply_correction` checks the ACTIVE target's `created_by_id == actor
  person_id` and raises `CorrectionNotAllowed` (`CORRECTION_NOT_ALLOWED`,
  HTTP 403) otherwise.
- The n8n picker still lists only the caller's own rows (defence in depth), but
  it is no longer the only thing enforcing the policy.
- If Erick later decides to allow cross-correction, it becomes an explicit flag
  on `apply_correction` + a documented change here.

Tests: `test_apply_correction.py::test_cannot_correct_another_persons_transaction`,
`test_api_corrections.py::test_cannot_correct_another_users_transaction`.

### Network

Do **not** attach `ledger-api` to `docker_gonex-network` (it would gain reach
to 7 unrelated services — against PHASE-2.7 §8, PHASE-2.11 §5). Create a small
dedicated network `ledger-net` and connect **only** `ledger-api` and
`gonex-n8n` to it; `ledger-api` also joins whatever network reaches
`gonex-postgres` (likely `docker_gonex-network` for the DB only, or a second
dedicated `ledger-db-net` if the operator prefers). n8n reaches the API as
`http://ledger-api:8000`.

---

## Part 3 — n8n workflow A: register a transaction

Built in the n8n UI (2.12). All user-facing text is fixed templates (no NLG,
PHASE-2.10 §26). `chat_id = message.chat.id` (== the user's private chat).

```
1. Telegram Trigger  (updates: message, callback_query)

2. IF  "private chat & known sender"          <-- Codex #2
     chat.type == "private"
     AND from.id is one of the two authorised telegram_user_id
   false -> reply "Este bot es privado." and STOP   (no state write)

3. Redis GET  mlbot:conv:{{chat_id}}   -> state (or empty)

4. Switch on state.step:

   (none) / IDLE
     -> send "¿Qué ocurrió?" + 5 inline buttons (event_type, texts per §8)
     -> Redis SET mlbot:conv:{{chat_id}} = {step:"WAITING_EVENT_TYPE"} EX 1800

   WAITING_EVENT_TYPE  (callback_query with an event_type)
     -> state {step:"WAITING_TRANSACTION_TEXT", event_type}
     -> send "¿Cuánto fue y en qué?  Ej: S/ 35.50 taxi"

   WAITING_TRANSACTION_TEXT  (message text)
     -> state.pending_raw_text = text; step = "WAITING_DATE"
     -> send date buttons [Hoy][Ayer][Otra fecha][Cancelar]

   WAITING_DATE
     Hoy/Ayer  -> compute date in America/Lima; step = "WAITING_CONFIRMATION"
     Otra fecha -> ask for YYYY-MM-DD, validate shape, then WAITING_CONFIRMATION
     -> send the summary (event label, amount text as typed, date) + [CONFIRMAR][CANCELAR]

   WAITING_CONFIRMATION
     CANCELAR -> Redis DEL; send "Cancelado."
     CONFIRMAR ->
       idempotency_key = "telegram:{{chat_id}}:update:{{update_id}}"   (of THIS confirm)
       state.pending_idempotency_key = idempotency_key; step = "PROCESSING"; Redis SET EX 1800
       HTTP Request  POST http://ledger-api:8000/api/v1/transactions
         header X-API-Key: (Header Auth credential)
         body { telegram_user_id, event_type, raw_text: pending_raw_text,
                event_date, idempotency_key }
       on 2xx:
         Redis DEL
         reply "✓ Registrado ..." with data.balance  (§16 wording; the balance
              shown is the running total, may differ from this amount)
         send notification to the OTHER user's chat  (§17 template)
       on 4xx:  map data.error.code -> friendly message (table below); keep
                state at WAITING_CONFIRMATION; offer [REINTENTAR][CANCELAR]
       on timeout / no response:  keep state; "No pude confirmar todavía,
                puedes reintentar."   Retry reuses pending_idempotency_key (§22).

5. Any unexpected callback while step == "PROCESSING": ignore (§15) — do not
   fire a second POST.
```

Error-code → user message (from PHASE-2.10 §21, codes are PHASE-2.5 §17):

| code | message |
|---|---|
| `PARSER_FAILED` | "No entendí el monto. Escribe algo como: `S/ 35.50 taxi`" |
| `INVALID_AMOUNT` | "El monto no es válido (debe ser positivo, con máximo 2 decimales)." |
| `INVALID_EVENT_DATE` | "La fecha no es válida o está en el futuro." |
| `INVALID_EVENT_TYPE` | "Tipo de operación no reconocido." (should not happen from buttons) |
| `UNKNOWN_TELEGRAM_USER` | "No estás autorizado para usar este bot." |
| `DUPLICATE_IDEMPOTENCY_KEY` | "Esa operación ya fue registrada con otros datos." |
| `INTERNAL_ERROR` / timeout | "Hubo un problema. Intenta de nuevo en un momento." |

---

## Part 4 — n8n workflow B: correct a transaction

Trigger: the `/corregir` command (or a persistent "Corregir un registro"
button). Same private-chat / known-sender guard as A.

```
1. HTTP GET http://ledger-api:8000/api/v1/transactions
     ?telegram_user_id={{from.id}}&status=active&limit=5   (X-API-Key)
   -> if empty: "No tienes registros para corregir."
   -> else: show them as buttons  "30 ago — S/ 35.50 — Taxi"  [1][2][3][Cancelar]
      store the chosen transaction id in state.pending_correction_target_id

2. "¿Qué deseas corregir?"  [El tipo][El monto/descripción][La fecha][Todo][Cancelar]
   -> record which fields are in scope; collect ONLY those (reuse A's prompts).
      A field not chosen is simply NOT sent -> the API keeps the target's value
      (amount-only and description-only corrections are supported).      <-- Codex #5

3. Comparative summary (MANDATORY, §18.3):
      Antes:  <old type> — S/ <old amount> — <old desc> — <old date>
      Después: <new ...>
   [CONFIRMAR][CANCELAR]

4. CONFIRMAR ->
     idempotency_key = "telegram:{{chat_id}}:update:{{update_id}}"
     step = "PROCESSING_CORRECTION"; Redis SET EX 1800
     HTTP POST http://ledger-api:8000/api/v1/transactions/{{target_id}}/corrections
       body { telegram_user_id, idempotency_key,
              event_type?,           <- only if "tipo"/"todo"
              event_date?,           <- only if "fecha"/"todo"
              raw_text?              <- only if "monto/descripción"/"todo"
              # OR structured amount?/description? individually — never both raw_text and structured
            }
     on 2xx: Redis DEL; "✓ Corrección aplicada ..." + new balance; notify the other user (§18.6)
     on 409 TRANSACTION_NOT_ACTIVE: "Este registro ya fue corregido antes." [VER REGISTRO ACTUAL][CANCELAR]  (§18.7)
     on 403 CORRECTION_NOT_ALLOWED: "Solo puedes corregir tus propios registros."
     on 404 TRANSACTION_NOT_FOUND: "No encontré ese registro."
```

n8n never resolves the supersession chain itself (§18.7) — the API does.

---

## Part 5 — Manual runbook (Erick executes; no agent touches the VPS)

Do the steps in order. Stop and report if any step's output is unexpected.
Keep every token/password out of shell history — put it in a variable set with
a leading space (`  VAR=...`) or a local file, never inline in a command that
gets logged.

### Step 0 — Redis auth check (read-only)

```
docker exec gonex-n8n sh -c 'redis-cli -h gonex-redis ping'
```
Expect `PONG`. If `NOAUTH Authentication required`, note the Redis password
(from `~/gonex/docker/.env` or the redis container env) for the n8n credential.

### Step 1 — dedicated network

```
docker network create ledger-net
docker network connect ledger-net gonex-n8n
```
Rollback: `docker network disconnect ledger-net gonex-n8n && docker network rm ledger-net`.

### Step 2 — project DB + least-privilege role in gonex-postgres

As a Postgres admin **inside psql** (`\du` etc. only work inside psql or via
`psql ... -c '\du'`):

```
psql -h <admin-host> -U <admin> -c "CREATE ROLE money_ledger_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '  <strong-pw>'"
psql -h <admin-host> -U <admin> -c "CREATE DATABASE personal_finance_bot OWNER money_ledger_app"
```
Record `<strong-pw>` privately. Rollback:
`DROP DATABASE personal_finance_bot; DROP ROLE money_ledger_app;`.

### Step 3 — build + migrate + run `ledger-api` (interim; Block 8 automates this)

From the repo on the VPS (or push the image):

```
docker build -t money-ledger:interim .

# run the migration once
docker run --rm --network docker_gonex-network \
  -e DB_HOST=gonex-postgres -e DB_PORT=5432 -e DB_NAME=personal_finance_bot \
  -e DB_USER=money_ledger_app -e DB_PASSWORD="  <strong-pw>" \
  money-ledger:interim alembic upgrade head

# apply the column-scoped production grants (as the schema owner / admin)
psql -h <admin-host> -U <admin> -d personal_finance_bot \
  -v app_role=money_ledger_app -f scripts/production_grants.sql

# start the API on both networks: ledger-net (for n8n) + docker_gonex-network (for the DB)
docker run -d --name ledger-api --restart unless-stopped \
  --network ledger-net \
  -e DB_HOST=gonex-postgres -e DB_PORT=5432 -e DB_NAME=personal_finance_bot \
  -e DB_USER=money_ledger_app -e DB_PASSWORD="  <strong-pw>" \
  -e API_INTERNAL_TOKEN="  <api-token>" -e ENVIRONMENT=production \
  money-ledger:interim
docker network connect docker_gonex-network ledger-api
```
Record `<api-token>` privately (a fresh strong value; NOT the DB password).
Rollback: `docker rm -f ledger-api`.

Verify: `docker exec gonex-n8n sh -c 'wget -qO- http://ledger-api:8000/api/v1/health'`
→ `{"status":"ok"}`.

### Step 4 — n8n credentials

In the n8n UI → Credentials:
- **Telegram API**: paste the `@CuentasDN_bot` token.
- **Header Auth**: name `X-API-Key`, value = `<api-token>` from step 3.
- **Redis** (if step 0 showed auth): host `gonex-redis`, port `6379`, password.

### Step 5 — build workflows A and B

Follow Parts 3 and 4 node by node. **Keep both workflows INACTIVE.**
Rollback: delete the workflows (never activated).

### Step 6 — capture the two `telegram_user_id`

Before any webhook is set, both Erick and Mamá send any message to
`@CuentasDN_bot`, then:

```
  TOKEN=<paste>   # leading space
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | jq '.result[].message.from | {id, first_name}'
unset TOKEN
```
Record the two `id` values.

### Step 7 — seed exactly two Person rows

```
psql -h <host> -U money_ledger_app -d personal_finance_bot -c \
"INSERT INTO person (id, telegram_user_id, name) VALUES
   (gen_random_uuid(), '<erick_id>', 'Erick'),
   (gen_random_uuid(), '<mama_id>',  'Mamá');"
```
Rollback: `UPDATE person SET is_active = false;` (never `DELETE` — keep it as
data).

### Step 8 — activate & set the webhook (the one real production change)

1. `getWebhookInfo` again, confirm still clean (already recorded).
2. Activate **workflow A** in n8n → n8n registers the Telegram webhook to its
   production URL automatically. (Or set it explicitly with `setWebhook`.)
3. Activate **workflow B**.

Rollback: deactivate both workflows, then
`curl -s "https://api.telegram.org/bot${TOKEN}/deleteWebhook"`.

### Step 9 — end-to-end verification

- Erick: full happy path with `S/ 10.00 prueba` on `Hoy`. Confirm the `✓
  Registrado` reply with a balance.
- Mamá receives the notification.
- `GET /api/v1/balance` (with `X-API-Key`) shows `10.00`,
  `direction: mama_owes_erick` (for `erick_gasta_para_mama`).
- `/corregir` → pick it → change amount to `12.00` → confirm → balance `12.00`.
- Mamá tries `/corregir` on Erick's row → she does not see it in the picker;
  a direct API call would get `403 CORRECTION_NOT_ALLOWED`.

Report the results; that closes Block 6.

---

## Part 6 — Change & rollback register

| Change | Applied by | Rollback |
|---|---|---|
| Create `@CuentasDN_bot` (BotFather) | done | BotFather → `/deletebot` |
| `docker network create ledger-net` + connect n8n | step 1 | disconnect + `network rm` |
| DB `personal_finance_bot` + role `money_ledger_app` | step 2 | `DROP DATABASE` / `DROP ROLE` |
| `alembic upgrade head` (additive `0001`+`0002`) | step 3 | `alembic downgrade base` (no data yet) |
| `production_grants.sql` | step 3 | `REVOKE` / re-`GRANT ALL` to the role |
| `ledger-api` container | step 3 | `docker rm -f ledger-api` |
| n8n credentials | step 4 | delete credentials |
| Workflows A/B (inactive) | step 5 | delete workflows |
| 2 `Person` rows | step 7 | `UPDATE person SET is_active = false` |
| **Telegram webhook set to n8n** | step 8 | deactivate workflows + `deleteWebhook` |

Nothing here is applied until this register and Parts 2–5 are reviewed.

---

## Part 7 — still open

- **Redis auth** (runbook step 0 result).
- Exact final button/template wording (decided while building the workflows;
  semantics are locked by PHASE-2.10).
- Whether the interim `ledger-api` from step 3 is kept until Block 8 or Block 8
  redeploys from scratch — Erick's call during Block 8.
