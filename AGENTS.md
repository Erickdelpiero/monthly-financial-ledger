# AGENTS.md — rules for coding agents on this project

Read `.ai/project.md` and this file at the start of a task. Read
`.ai/decisions.md` before touching the domain, API, security, or migrations.

## Authority (PHASE-2.12 §6)

**You may, without asking:**

- read the repository and docs;
- create/modify application code and tests; run tests, linters, static analysis;
- create **local** commits;
- propose changes and document decisions;
- review the other agent's work.

**Requires Erick's explicit approval:**

- `git push` and `merge` — a human always pushes; no agent pushes code;
- anything touching production: the VPS, production PostgreSQL, n8n, the
  Telegram webhook, live infrastructure;
- destructive operations (`DROP`, deleting data) and potentially destructive
  migrations;
- secret / credential changes;
- architectural changes vs. what is closed in `architecture/` (2.1–2.12).

If an implementation would conflict with `architecture/`, do not invent a new
rule silently — flag the conflict and ask.

## Hard rules

- **Financial correctness never depends on an LLM.** Python is the single
  source of truth for signs, balance, validation, and corrections.
- **Append-only ledger.** Never `UPDATE` / `DELETE` a ledger row outside the
  correction service; never store the balance.
- **No `float` for money** — `Decimal` / `NUMERIC` only.
- **PostgreSQL only** (never SQLite), including in dev and tests.
- **Nothing sensitive in Git:** secrets, real financial data, real Telegram
  ids, `.env`, DB dumps, generated reports with real data. Tests use synthetic
  data.
- The backend is **never exposed to the internet**; n8n reaches it over an
  internal network with `X-API-Key`.

## Development & testing

- Layout: `src/` (`src/money_ledger/`). `requirements.txt` = runtime,
  `requirements-dev.txt` = tests. `venv` + `pip`.
- Tests run against a **real local PostgreSQL** named by `TEST_DATABASE_URL`;
  they skip if it is unset — never point them at production. `pytest -m docker`
  needs a Docker daemon and skips otherwise.
- Keep the whole suite green under `-W error`. Add a test for every new
  behaviour and every bug fixed.
- Branch `main`; simple feature branches when useful. Git worktrees are
  deferred.
