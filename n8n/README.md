# n8n workflows — Block 6

Two exports for n8n **2.12.3**, matching `docs/block-6-n8n-telegram.md` Parts 3
and 4:

| File | Workflow | Trigger |
|---|---|---|
| `workflow-a-registro.json` | **A – Registro** + router | `Telegram Trigger` (owns the bot webhook) |
| `workflow-b-correccion.json` | **B – Corrección** | `Execute Workflow Trigger` (called by A) |

Both import with `"active": false`. Credentials are referenced **by name only**
(`Telegram API`, `Header Auth`, `Redis`) — no tokens or values are in the JSON.

> **These were generated without a live n8n to validate against.** The graph,
> the routing, and all logic (in Code nodes) are complete, but some node
> *parameter* shapes — especially the Telegram inline-keyboard fields and the
> credential bindings — may need one click to confirm after import. Do the
> visual pass below before activating anything.

---

## Why A + B instead of two independent workflows

A Telegram bot allows **one webhook**. Two workflows each with a `Telegram
Trigger` on `@CuentasDN_bot` would fight over it. So:

- **A** owns the trigger. On `/corregir` (or while a correction is in
  progress) it calls **B** via the *Execute Workflow* node `Ejecutar
  correccion (B)`.
- **B** has no webhook. A sub-workflow runs even while `inactive`, so B stays
  `active:false` forever. **You only ever activate A.**

---

## Import (n8n UI → Workflows → Import from File)

1. **Import `workflow-b-correccion.json` first.** Open it once and **Save** so
   n8n assigns it an ID. Leave it inactive.
2. **Import `workflow-a-registro.json`.**
3. In A, open the node **`Ejecutar correccion (B)`** → the *Workflow*
   field currently says `REPLACE_WITH_WORKFLOW_B_ID` → pick
   **"Ledger B - Correccion (sub-workflow de A)"** from the dropdown → Save.
4. **Set the 3 `$env` vars on the `gonex-n8n` container** (runbook Step 4):
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_AUTHORIZED_IDS`, `TELEGRAM_OTHER_MAP`.
   The 6 keyboard-sending nodes are plain HTTP Request calls to
   `https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage`
   (the native `n8n-nodes-base.telegram` node does **not** support a
   dynamically-built inline keyboard — B6-8); the other two vars carry the
   auth list and the notify map (see the table below). Nothing to type into
   nodes after import. The native Telegram credential still covers the Trigger
   and every non-keyboard reply.

## The three project-specific values are `$env` vars (nothing to edit in n8n)

All three real-identifier values are read from the `gonex-n8n` container
environment at runtime, so a re-import never loses them and they stay out of
this public repo (`.ai/decisions.md` → "no real Telegram ids in Git").

| Read in | Code var | `$env` var | Format | Missing / bad → |
|---|---|---|---|---|
| A `Parse update` | `AUTHORIZED_IDS` | `TELEGRAM_AUTHORIZED_IDS` | `id1,id2` (comma-separated) | `[]` → every sender gets "Este bot es privado" |
| A `Handle API` | `OTHER` | `TELEGRAM_OTHER_MAP` | JSON `{"id1":"id2","id2":"id1"}` | `{}` → no cross-notification (main flow still works) |
| B `Handle corr` | `OTHER` | `TELEGRAM_OTHER_MAP` | same | same |

Both parse fail-closed (wrapped in `try/catch`). Set the vars in runbook
Step 4 alongside `TELEGRAM_BOT_TOKEN`.

> **Required for any of this to work:** n8n ≥ 2.0 blocks `$env` in Code nodes
> and expressions by default (`N8N_BLOCK_ENV_ACCESS_IN_NODE`, default `true`).
> Set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in the n8n service's `environment:`
> and recreate the container, or every `$env.*` read silently returns
> `undefined` — the symptom that blocked Block 6 for a whole cycle (B6-9).
> Trade-off: this enables `$env` for **every** workflow on that n8n instance.

## Confirm the API URL

All HTTP Request nodes call `http://ledger-api:8000/api/v1/...`. This assumes
the API container is named `ledger-api` and shares the `ledger-net` network
with `gonex-n8n` (runbook Steps 1 and 3). If you named it differently, update:
- A: `POST /transactions`
- B: `GET /transactions B`, `POST /corrections B`

---

## Visual verification checklist (do this before activating A)

For **every node that has a credential**, open it and check the credential
dropdown shows the right one:

- `Telegram Trigger` + the native `Telegram` sendMessage nodes (`Bot privado`,
  `TG: texto`, `TG: registrado`, `TG: notificar`, `TG: seguir`; B `TG: texto B`,
  `TG: ok B`, `TG: notificar B`) → **Telegram API**
- Redis nodes → **Redis**
- The **ledger-API** HTTP Request nodes (`POST /transactions`; B
  `GET /transactions B`, `POST /corrections B`) → **Header Auth**
- The **Telegram-API** HTTP Request nodes (`TG: con botones`, `TG: error`,
  `TG: preguntar pendiente`; B `TG: botones B`, `TG: picker B`, `TG: err B`) →
  **no credential**; they authenticate via `{{ $env.TELEGRAM_BOT_TOKEN }}` in
  the URL.

Then:

- [ ] `Router` (A) reads the update fields from `$('Parse update')` and
      `Correccion SM` (B) from `$('Inicio (desde A)')` — **not** from `$json` /
      `$input`. The Redis `get` node (`Load state` / `Cargar estado`) returns
      only `{ stateRaw }` and drops everything else; a re-export must not
      "simplify" these back to `$input`. (See B6-6.)
- [ ] A `Telegram Trigger`: *Updates* = `message` and `callback_query`.
- [ ] A `Ejecutar correccion (B)`: points at workflow B (not the placeholder).
- [ ] Every `Switch` node: *Mode* = **Expression**, and *Number of Outputs*
      matches the number of connected branches (A `Route`=**5**, A `Estado`=3,
      A `Route SM`=4, A `Route API`=2; B `Estado B`=3, B `Route SM B`=5,
      B `Route corr`=2). If n8n shows fewer output dots than connections,
      set *Number of Outputs* manually.
- [ ] The **6** keyboard-sending nodes (A `TG: con botones`, `TG: error`,
      `TG: preguntar pendiente`; B `TG: botones B`, `TG: picker B`,
      `TG: err B`) are **HTTP Request** nodes (`POST` to
      `…/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage`, `Body Content Type` =
      JSON). The Code nodes emit `n8nKeyboard` already in Telegram's native
      `{ inline_keyboard: [[{ text, callback_data }]] }` shape; the HTTP body
      passes it straight through as `reply_markup`. Do **not** convert these
      back to the native Telegram node — it silently drops dynamic keyboards
      (B6-8).
- [ ] `{{ $env.TELEGRAM_BOT_TOKEN }}` resolves: `gonex-n8n` has the env var and
      `N8N_BLOCK_ENV_ACCESS_IN_NODE` is not `true`. Test-run `TG: con botones`
      and confirm the URL is not `…/botundefined/…`.
- [ ] A `IF decision`: condition is `decision` **equals** `switch`; *true*
      output → `Ejecutar correccion (B)`, *false* → `Redis: set (limpiar)`.
- [ ] A `IF: hay a quien notificar` / B `IF: notificar B`: condition is
      `notifyChatId` **is not empty**; the *true* output goes to the notify
      node, the *false* output goes nowhere.
- [ ] Redis nodes: `Get` nodes have *Property Name* `stateRaw` and *Key Type*
      `string`; `Set` nodes have *Expire* on with *TTL* `1800`.
- [ ] Every **native** Telegram `sendMessage` node has *Append n8n Attribution*
      = **off** (`additionalFields.appendAttribution: false`) — otherwise the
      reply ends with " This message was sent automatically with n8n". (The
      HTTP-Request sends don't have this problem.)
- [ ] Run **`Load state`** once with *Execute Node* on a hand-made pinned item
      `{ "chatId": 123 }` to confirm the Redis credential connects (it returns
      an empty `stateRaw` for a missing key — that is fine).

Nothing above changes behaviour; it only confirms n8n parsed the export the way
this repo intended. When it all checks out, follow runbook Step 8 to activate A
and set the webhook, then Step 9 to verify end to end.

---

## State model (for reference while reviewing the Code nodes)

Redis key `mlbot:conv:<chat_id>`, JSON value, `EX 1800`. Steps:

```
Registration (A):  IDLE → WAITING_EVENT_TYPE → WAITING_TRANSACTION_TEXT
                   → WAITING_DATE [→ WAITING_DATE_MANUAL] → WAITING_CONFIRMATION
                   → PROCESSING → (key deleted)
                   on API error: PROCESSING → WAITING_CONFIRMATION (retry with the
                     same idempotency_key)
Correction (B):    (fresh /corregir) → WAITING_CORRECTION_SELECTION
                   → WAITING_CORRECTION_SCOPE
                   → WAITING_CORRECTION_EVENT_TYPE / _TEXT / _DATE [/ _DATE_MANUAL]
                   → WAITING_CORRECTION_CONFIRMATION → PROCESSING_CORRECTION
                   → (key deleted)
                   on API error: PROCESSING_CORRECTION → WAITING_CORRECTION_CONFIRMATION
                     (via `Redis: revertir (err) B`, retry with the same key)
```

If the user types `/corregir` while a registration is unfinished, A does **not**
silently discard it (PHASE-2.10 §20): it sets `pending_prompt` on the state and
sends *Continuar registro / Cancelar y corregir*. "Continuar" clears the marker;
"Cancelar y corregir" forwards to B with `forceCorrection`.

`idempotency_key = telegram:<chat_id>:update:<update_id>`, generated when the
summary/confirmation screen is shown and reused on every retry.
