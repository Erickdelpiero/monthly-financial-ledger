# Project: Personal Expense Ledger Bot

A small personal Telegram bot that keeps a **bilateral money-flow ledger**
between two people (Erick and his mother). Deterministic financial logic in
Python (FastAPI); PostgreSQL is the source of truth; n8n orchestrates the
Telegram conversation. The ledger is **append-only** — a correction creates a
new row and marks the old one `SUPERSEDED`; the balance is always *derived*,
never stored. The project is also a pilot for Erick's AI-assisted engineering
workflow: per implementation block, **Claude Code implements and Codex reviews**.

## Where things are

| | |
|---|---|
| `architecture/` | The closed, approved spec — Phase 1 + Phase 2.1–2.12. Source of truth for any domain / API / security question. |
| `docs/decisions/block-1-followups.md` | Running, curated log of implementation decisions and cross-doc fixes made during the build (F1–F4, N1–N3, and per-cycle review outcomes). |
| `docs/block-6-n8n-telegram.md` | Block 6 design + the manual n8n/VPS runbook. |
| `AGENTS.md` / `CLAUDE.md` | Agent rules (general / Claude Code specific). |
| `src/money_ledger/` | Code: `models/` `domain/` `services/` `parsing/` `api/`. Plus `migrations/`, `tests/`. |
| `.ai/decisions.md` | The short list of settled decisions, so agents don't re-litigate them. |

## How to work here

Read this file and `AGENTS.md` (or `CLAUDE.md`) at the start of a task; read
`.ai/decisions.md` before touching the domain, API, security, or migrations.
Open `architecture/` or the code only when the task actually needs it — don't
load the whole history into every prompt.

Block-by-block status lives in `docs/decisions/block-1-followups.md`.
