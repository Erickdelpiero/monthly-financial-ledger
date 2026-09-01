# CLAUDE.md — Claude Code on this project

`AGENTS.md` has the rules for every agent. This file adds only what is specific
to Claude Code — it does not repeat `AGENTS.md`.

## Role in the pilot

Per implementation block: **Claude Code implements, Codex reviews.** After
Codex's feedback, apply the fixes, re-run the full suite twice under `-W error`,
and record the outcome in `docs/decisions/block-1-followups.md` (an `F`/`N`/`C`/`B`
entry). Do not spawn subagents unless asked.

## Running the tests

The suite needs a real local PostgreSQL. Until `docker compose up -d db` is
usable here, it has been run against an ephemeral userspace instance:

```bash
pip install pgserver          # once, in the venv
# start a throwaway server, create a least-privilege role + money_ledger_test DB,
# then:
TEST_DATABASE_URL=postgresql+psycopg://<role>:<pw>@/money_ledger_test?host=<sockdir> \
  .venv/bin/python -m pytest -q -W error
```

Tear the ephemeral server down and remove `pgserver` from the venv afterwards so
`.venv` still matches `requirements-dev.txt`.

## Must not do here

- Never `git push`, open PRs, or merge (see `AGENTS.md`).
- Never SSH to or modify the VPS, n8n, `gonex-redis`, or the Telegram webhook.
  Produce a step-by-step manual runbook for Erick instead (pattern:
  `docs/block-6-n8n-telegram.md` Part 5).
- Never ask for or handle the `@CuentasDN_bot` token or production credentials.
