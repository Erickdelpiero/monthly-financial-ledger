# X1 — Data plan for the Block 6 E2E test rows (one-off)

Companion to `docs/decisions/block-1-followups.md` §X1 (the inverted
`mama_devuelve` / `erick_devuelve` sign fix). §X1 covers the **code + tests +
architecture erratum**; this file is the **one-off data event**: what to do with
the four `erick_gasta_para_mama` / `mama_devuelve` rows the Block 6 E2E left in
**production**, so the real balance ends at `S/ 0.00` without ever using
`DELETE`, consistent with the append-only design.

This is **not** part of the repeatable deploy runbook — do not fold it into
`docs/block-8-cicd-deploy.md`. It happens once, around the deploy that ships the
§X1 sign fix.

Status: **plan only — nothing executed, nothing deployed.** Ratified by Erick
(the sign change). The steps below are run by Erick as operator on the VPS.

---

## The rows in production

Reconstructed from the reported E2E sequence (confirm in Phase 0):

| Row | `event_type` | Amount | `status` | Note |
|---|---|---:|---|---|
| **A** | `erick_gasta_para_mama` | 10.00 | ACTIVE | — |
| **B** | `erick_gasta_para_mama` | 5.00 | **SUPERSEDED → C** | already out of the balance; never touched |
| **C** | `erick_gasta_para_mama` | 7.00 | ACTIVE | the correction of B |
| **D** | `mama_devuelve` | 17.00 | ACTIVE | the "Mama me devolvió dinero" button |

Balance **now** (old sign, `mama_devuelve = -1`):
`-10 -7 -17 = -34.00` → "Mamá debe a Erick: S/ 34.00" (matches the bug report).

Balance **after the §X1 deploy** (new sign, `mama_devuelve = +1`), **data
untouched**: `-10 -7 +17 = 0.00` → "No hay deuda pendiente."

---

## Order: deploy first, then (optionally) relabel

**Deploy the sign fix first. Do not run any correction before the deploy.**

Three design facts force this:

1. **`signed_effect` is never stored.** `get_balance` recomputes it from
   `event_type` on every read (`domain/balance.py`). The moment the new image
   runs, every existing `*_devuelve` row silently changes its contribution — no
   migration, no row edit. The target end-state balance is only defined once the
   new sign is live.

2. **`amount` is strictly positive** (`domain/money.py`: `amount must be
   positive`). A correction can never zero a row out or delete it — it always
   inserts a new ACTIVE row that contributes ±amount. Append-only ⇒ these rows
   can be *superseded*, never *removed*.

3. **A correction row inherits the same sign mechanism.** Forcing `S = 0` before
   the deploy (old sign) while D is still `mama_devuelve` S/17 (−17) requires the
   other ACTIVE rows to sum to +17. After the deploy D flips to +17, so
   `S = +17 +17 = +34.00` — the *same doubling bug, mirrored*, plus a wrong
   public balance in between and a second correction round. The only
   deploy-stable "correct-first" variant is to retype D from `mama_devuelve` to
   `mama_entrega_dinero` (+1 under both signs) — but that **falsifies the
   ledger** (records a fresh hand-over, not a return) and still ignores A and C.

Deploy-first sidesteps all of it: the corrected sign yields `S = 0.00` with the
rows exactly as they are, and the only cleanup left is **description-only**,
which by construction cannot move `S` (same `amount`, same `event_type` ⇒ same
`signed_effect`). It also makes the balance *correct* first, instead of routing
the weekly report Nora sees through wrong values.

**What the deploy alone achieves:** the real balance goes to `S/ 0.00`. The
optional corrections below only *relabel* A/C/D as test data so the monthly
report for that month is not misleading — they are not needed for the balance.

---

## Runbook (Erick, on the VPS)

`ledger-api` has no host port — reach it from inside its own container. This
method uses the container's Python and reads `API_INTERNAL_TOKEN` from its
environment, so **no token or credential is typed**.

Helper (paste once into the VPS shell session):

```bash
api() {
  # api GET  /api/v1/balance
  # api POST /api/v1/transactions/<id>/corrections '<json-body>'
  local method="$1" path="$2" body="${3:-}"
  docker exec -i ledger-api python - "$method" "$path" "$body" <<'PY'
import os, sys, json, urllib.request, urllib.error
method, path, body = sys.argv[1], sys.argv[2], sys.argv[3]
url = "http://127.0.0.1:8000" + path
data = body.encode() if body else None
req = urllib.request.Request(url, data=data, method=method,
    headers={"X-API-Key": os.environ["API_INTERNAL_TOKEN"],
             "Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=5)
    print(r.status); print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(e.code); print(e.read().decode())
PY
}
```

### Phase 0 — snapshot (read-only, BEFORE the deploy)

```bash
api GET /api/v1/balance
# expected: {"balance":"34.00","currency":"PEN","direction":"mama_owes_erick"}

api GET "/api/v1/transactions?telegram_user_id=<TG_ID_ERICK>&status=all&limit=20"
# record id / event_type / amount / description / event_date / status /
# created_by / superseded_by for A, B, C, D. Confirm the table above.
```

- If the balance is not `34.00`, or rows other than A/B/C/D exist → **stop** and
  reassess; the ledger has something else in it.
- Note **D**'s `created_by`. If it is not Erick's person id, D's correction is
  done by Mamá (Phase 3).
- Save this output to a file — it is the evidence and the logical rollback
  reference.

### Phase 1 — deploy the §X1 sign fix

Normal pipeline (`deploy.yml` → `mfl-deploy-run.sh`): CI green → `production`
approval → GHCR build → `migrate` (no new migration — no-op) → `up -d api` →
health gate. **No schema or data change in this deploy** — image only; the sign
recomputes itself.

### Phase 2 — verify the balance is already 0.00 (**hard gate**)

```bash
api GET /api/v1/balance
# expected: {"balance":"0.00","currency":"PEN","direction":"no_debt"}
```

- `0.00` / `no_debt` → the balance goal is met. Proceed to Phase 3 only to
  relabel.
- **Anything else → run no corrections.** Re-enumerate (Phase 0 call), diff
  against the snapshot: a row appeared/vanished, or D was not `mama_devuelve`.
  Diagnose first.

### Phase 3 — (recommended, optional) relabel the test rows

**Description-only** corrections: same `amount`, `event_type`, `event_date` ⇒
identical `signed_effect` ⇒ the balance stays `0.00` throughout. Each inserts a
new ACTIVE row and marks the previous one SUPERSEDED (append-only, no DELETE).

One per row, using the **current ACTIVE ids** from Phase 0 (A, C, D — **B is not
touched**). Unique `idempotency_key` per call.

```bash
# --- Row A (Erick) ---
api POST "/api/v1/transactions/<ID_A>/corrections" \
 '{"telegram_user_id":"<TG_ID_ERICK>","idempotency_key":"manual-x1-label-A",
   "description":"[PRUEBA E2E Bloque 6 — sin efecto real] <original description of A>"}'

# --- Row C (Erick) ---
api POST "/api/v1/transactions/<ID_C>/corrections" \
 '{"telegram_user_id":"<TG_ID_ERICK>","idempotency_key":"manual-x1-label-C",
   "description":"[PRUEBA E2E Bloque 6 — sin efecto real] <original description of C>"}'

# --- Row D (whoever created D) ---
api POST "/api/v1/transactions/<ID_D>/corrections" \
 '{"telegram_user_id":"<TG_ID_OF_D_CREATOR>","idempotency_key":"manual-x1-label-D",
   "description":"[PRUEBA E2E Bloque 6 — devolución de prueba, sin efecto real] <original description of D>"}'
```

- **Ownership rule** (`ledger_service.py`, `CorrectionNotAllowed` / 403): the
  body's `telegram_user_id` must match the row's `created_by`. A and C are
  Erick's. For D use the creator's id — if that is Mamá, she runs it from her
  Telegram, or Erick runs it as operator with her id (documented maintenance,
  with her consent).
- Every response must be `200` with `"balance"` → `"0.00"` / `"no_debt"`. If a
  balance comes back different, **stop**.

**Telegram `/corregir` alternative:** works, but the n8n flow has no
description-only scope — "El monto/descripción" asks for amount *and* description
together. If used, **re-type the exact same amount** (`S/ 10.00 …`, `S/ 7.00 …`,
`S/ 17.00 …`); a different amount moves the balance off `0.00`. The direct API
path is safer here.

### Phase 4 — final verification

```bash
api GET /api/v1/balance
# {"balance":"0.00","currency":"PEN","direction":"no_debt"}

api GET "/api/v1/reports/monthly?year=<YYYY>&month=<MM>"   # month of the test event_date
# 3 movements (A', C', D'), each description carrying the [PRUEBA E2E …] marker,
# embedded balance "0.00" / "no_debt"
```

Weekly report (`/reports/weekly`) → "No hay deuda pendiente. Saldo: S/ 0.00".

---

## What this does NOT do

- **It does not delete the test rows.** Append-only + strict `amount > 0` ⇒ A, C,
  D stay as three line items in that month's report, netting to zero and labeled
  as a test. Removing them from the report entirely would need `DELETE` or a
  status that does not exist — outside the design. If that matters for audit, the
  decision to take is a design one (e.g. a `status = TEST` excluded from
  reports), not a data edit.
- **It does not touch row B** — already SUPERSEDED, already out of the balance.
- **No data migration.** The deploy changes only the image; the sign recomputes
  on every read.

---

## Classification

| Point | Class |
|---|---|
| Order **deploy → verify 0.00 → (relabel)**. Pre-deploy corrections re-create the doubling in mirror or falsify `event_type`. | **Necesaria** (procedure) |
| Phase 2 as a hard gate: if the post-deploy balance is not `0.00`, run no corrections. | **Necesaria** |
| Relabel A/C/D with description-only corrections via the direct API (not Telegram) to avoid touching the amount. | **Recomendable** |
| The 3 test lines stay visible (net zero) in that month's report; no append-only way to hide them. | **Sin objeción** (documented design limit) |
