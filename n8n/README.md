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

## Fill in the three project-specific values (search for `TODO (Step 8)`)

> **Edit these in the n8n UI on the VPS only — never in this repo.** The two
> `telegram_user_id` are real personal identifiers and this is a public repo
> (`.ai/decisions.md` → "no real Telegram ids in Git"). The committed JSON
> keeps the `TODO (Step 8)` placeholders; the real values live only in the
> imported workflows on the VPS. If you ever re-export the workflows for the
> repo, blank these three constants back to `[]` / `{}` first.

| Where | Constant | Value |
|---|---|---|
| A → `Parse update` (Code) | `AUTHORIZED_IDS` | `[<erick_id>, <mama_id>]` — the two `telegram_user_id` as **numbers** (from runbook Step 6). Empty = nobody allowed. |
| A → `Handle API` (Code) | `OTHER` | `{ "<erick_id>": "<mama_id>", "<mama_id>": "<erick_id>" }` — maps a sender to the other person's chat id (for a bot, chat id == user id), keys as **strings**. |
| B → `Handle corr` (Code) | `OTHER` | same map as above. |

If `AUTHORIZED_IDS` is left empty the bot will only ever reply "Este bot es
privado" — that is the fail-closed default; fill it before Step 9.

## Confirm the API URL

All HTTP Request nodes call `http://ledger-api:8000/api/v1/...`. This assumes
the API container is named `ledger-api` and shares the `ledger-net` network
with `gonex-n8n` (runbook Steps 1 and 3). If you named it differently, update:
- A: `POST /transactions`
- B: `GET /transactions B`, `POST /corrections B`

---

## Visual verification checklist (do this before activating A)

For **every node that has a credential** (all `Telegram`, `Redis`, and HTTP
Request nodes), open it and check the credential dropdown shows the right one:

- Telegram nodes + `Telegram Trigger` → **Telegram API**
- Redis nodes → **Redis**
- HTTP Request nodes → **Header Auth** (Generic Credential Type → Header Auth)

Then:

- [ ] A `Telegram Trigger`: *Updates* = `message` and `callback_query`.
- [ ] A `Ejecutar correccion (B)`: points at workflow B (not the placeholder).
- [ ] Every `Switch` node: *Mode* = **Expression**, and *Number of Outputs*
      matches the number of connected branches (A `Route`=**5**, A `Estado`=3,
      A `Route SM`=4, A `Route API`=2; B `Estado B`=3, B `Route SM B`=5,
      B `Route corr`=2). If n8n shows fewer output dots than connections,
      set *Number of Outputs* manually.
- [ ] The **6** nodes that send inline keyboards (A `TG: con botones`,
      A `TG: error`, A `TG: preguntar pendiente`; B `TG: botones B`,
      B `TG: picker B`, B `TG: err B`):
      *Reply Markup* = **Inline Keyboard**. The keyboard is passed as an
      expression (`$json.n8nKeyboard` / a literal). If n8n won't accept the
      expression on the keyboard field, switch that field to "expression" mode
      (the small `fx`), or rebuild the keyboard rows by hand from the Code
      node's structure (`rows[].row.buttons[].button.{text, additionalFields.callback_data}`).
- [ ] A `IF decision`: condition is `decision` **equals** `switch`; *true*
      output → `Ejecutar correccion (B)`, *false* → `Redis: set (limpiar)`.
- [ ] A `IF: hay a quien notificar` / B `IF: notificar B`: condition is
      `notifyChatId` **is not empty**; the *true* output goes to the notify
      node, the *false* output goes nowhere.
- [ ] Redis nodes: `Get` nodes have *Property Name* `stateRaw` and *Key Type*
      `string`; `Set` nodes have *Expire* on with *TTL* `1800`.
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
