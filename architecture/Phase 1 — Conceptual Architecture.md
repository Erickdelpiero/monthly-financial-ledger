# Phase 1 — Conceptual Architecture
## Personal Finance Flow Bot

**Status:** Approved  
**Phase:** 1 — Conceptual Analysis & Architecture  
**Project:** Personal pilot / Agent Framework Laboratory  
**Primary interface:** Telegram  
**Orchestrator:** n8n  
**Business logic:** Python  
**Persistence:** PostgreSQL  
**AI strategy:** Deterministic parser + LLM fallback

---

## 1. Purpose

Build a small personal Telegram bot that maintains a bilateral financial ledger between Erick and his mother.

The purpose of this pilot is twofold:

1. Build a useful, reliable application.
2. Experiment with a professional development workflow using **Claude Code + Codex**, including implementation, review, security analysis, and human approval.

The pilot must remain intentionally small and avoid unnecessary AI or infrastructure complexity.

---

## 2. Problem

Erick and his mother exchange money irregularly.

Typical situations include:

- Mother gives Erick money to purchase something.
- Erick spends money on behalf of his mother.
- Erick gives money to his mother.
- One person returns money to the other.
- A transaction may be recorded days after it actually occurred.

Currently, these movements are tracked manually and reconciled periodically.

The system should maintain a continuously updated net balance and automatically provide:

- weekly status;
- monthly detailed report.

---

## 3. Scope

### Included

- Two authorized Telegram users.
- Telegram-based transaction registration.
- Explicit transaction-type selection through buttons.
- Amount and description extraction.
- Deterministic financial calculations in Python.
- PostgreSQL persistence.
- Append-only transaction ledger.
- Transaction correction without overwriting historical records.
- Event date and registration timestamp.
- Weekly balance notification.
- Monthly transaction report.
- n8n orchestration.
- Deterministic templates for user-facing responses.
- LLM fallback for failed amount/description extraction.
- Security controls suitable for a public GitHub repository.

### Explicitly excluded

- Conversational chatbot.
- Dynamic NLG.
- LLM-based financial calculations.
- LLM-based transaction classification.
- Multi-user platform.
- Web frontend.
- RAG/vector database.
- Autonomous financial decisions.
- Production database modification by agents without human approval.
- Unnecessary microservices or infrastructure.
- OpenCode/Ollama in this pilot.

---

## 4. Core Design Principles

### 4.1 Deterministic financial system

Financial calculations must never depend on an LLM.

Python is the authoritative implementation of:

- balance calculations;
- transaction validation;
- business rules;
- reconciliation logic.

### 4.2 LLM as a constrained component

The LLM is not the source of truth.

When used, it is restricted to extracting structured information from user text.

It must never determine:

- transaction type;
- transaction direction;
- financial balance;
- authorization;
- database state.

### 4.3 Explicit user intent

The transaction type is selected explicitly through Telegram buttons.

The system does not infer financially significant intent from free-form language.

### 4.4 Append-only history

Historical financial events must not be silently overwritten.

Corrections create new records while preserving the original event and its history.

### 4.5 Human authority

Erick is the final authority.

Agents may analyze, implement, test, review and propose changes, but important decisions remain subject to human approval.

---

# 5. Financial Model

The system maintains one net balance:

`S > 0` → Erick owes money to his mother.

`S < 0` → His mother owes money to Erick.

`S = 0` → Neither party has a net debt.

The five initial event types are:

| Event | Effect on S |
|---|---:|
| `mama_entrega_dinero` | `+amount` |
| `erick_gasta_para_mama` | `-amount` |
| `erick_entrega_dinero` | `-amount` |
| `mama_devuelve` | `-amount` |
| `erick_devuelve` | `+amount` |

### Example

Mother gives Erick S/100:

`S = +100`

Erick spends S/70 for his mother:

`S = +100 - 70 = +30`

Erick later spends the remaining S/30 for his mother:

`S = +30 - 30 = 0`

No separate "change/vuelto" entity is required. The remaining amount is represented naturally by the net balance.

### Scope clarification

`mama_entrega_dinero` represents money given as part of this bilateral financial account and intended to be reconciled through subsequent expenses or returns.

Gifts or unrelated transfers are outside the scope of this pilot.

---

# 6. Interaction Model

The Telegram interface identifies the sender through their Telegram `user_id`.

The transaction type is selected explicitly through buttons.

### Erick

- Mamá me dio dinero
- Gasté para mamá
- Le devolví a mamá
- Mamá me devolvió

### Mother

- Le di dinero a Erick
- Erick gastó para mí
- Le devolví a Erick
- Erick me devolvió

After selecting the transaction type, the user provides:

- amount;
- short description;
- event date.

Date selection should preferably use:

- Hoy
- Ayer
- Otra fecha

User-facing responses are deterministic templates.

The bot is not conversational.

---

# 7. NLU Strategy

The initial implementation deliberately prioritizes deterministic parsing.

```text
User input
    ↓
Deterministic parser
    ↓
Valid?
 ┌──┴──┐
Yes    No
 ↓      ↓
Data   LLM fallback
         ↓
      Validation
```

The parser attempts to extract:

- `amount`
- `description`

The LLM is only a fallback.

Its output must be structurally validated before entering the business logic.

The LLM must never produce or modify:

- `event_type`
- sender identity
- financial sign
- balance
- database operations.

The pilot should allow us to measure how often the LLM fallback is actually necessary.

A possible future experiment is to evaluate whether LLM-based extraction provides enough additional value to justify replacing or augmenting the deterministic parser.

---

# 8. Ledger

The ledger is append-only.

A transaction should conceptually contain at least:

- unique identifier;
- event type;
- amount;
- description;
- event date/time;
- registration timestamp;
- originating Telegram user;
- correction relationship/status where applicable.

The exact PostgreSQL schema, constraints, indexes and migration strategy belong to Phase 2.

---

# 9. Transaction Corrections

Historical transactions should not be silently overwritten.

When a transaction is incorrect:

```text
Original transaction
        ↓
Correction
        ↓
New transaction
```

The original remains available for audit/history and is excluded from the effective balance according to the correction model defined in Phase 2.

The user experience should remain simple.

The user should not need to remember internal transaction IDs.

A future implementation may expose recent transactions as selectable Telegram buttons for correction.

The exact correction UX belongs to Phase 2.

---

# 10. Dates

The system distinguishes:

### Event date

When the financial event actually occurred.

### Registration timestamp

When the event was entered into the system.

Example:

```text
Event:       August 20
Registered:  August 29
```

Both values are retained.

---

# 11. High-Level Architecture

```text
                    Telegram
                       │
             user_id + explicit buttons
                       │
                       ▼
                     n8n
                 Orchestration
                       │
                       ▼
                Python backend
                       │
             ┌─────────┴─────────┐
             │                   │
     Deterministic parser     LLM fallback
             │                   │
             └─────────┬─────────┘
                       ▼
                  Validation
                       │
                       ▼
                  PostgreSQL
                 Append-only
                       │
              ┌────────┴────────┐
              ▼                 ▼
        Weekly balance     Monthly report
              │                 │
              └────────┬────────┘
                       ▼
                      n8n
                       │
                       ▼
                   Telegram
```

---

# 12. Development and Deployment Philosophy

The normal development preference is:

```text
Ubuntu
   ↓
Local development
   ↓
Git
   ↓
GitHub
   ↓
CI/CD
   ↓
VPS
   ↓
Production
```

However, n8n already exists on the VPS and Telegram integration requires real external connectivity.

Therefore, Phase 2 must determine the most appropriate development architecture rather than assuming that every component must run locally.

The preferred database is PostgreSQL from the beginning, provided the existing VPS infrastructure supports it appropriately.

SQLite should only be introduced if PostgreSQL is genuinely impractical.

The goal is to minimize environment differences between development and production.

---

# 13. Security

The repository is intended to be public.

Security is therefore a requirement from the first commit.

Never commit:

- API keys;
- Telegram bot tokens;
- database credentials;
- n8n credentials;
- private environment variables;
- real financial records;
- real screenshots;
- sensitive personal information.

Use:

```text
.env
```

for secrets and:

```text
.env.example
```

for reproducible configuration documentation.

Testing data must be synthetic.

Before publication/push, the repository must undergo security and secret-exposure checks.

---

# 14. Agent Workflow

This pilot deliberately experiments with two coding agents:

- Claude Code
- Codex

Initial experiment:

```text
Claude Code
     ↓
Implementation
     ↓
Codex
     ↓
Independent review
```

The roles are not permanently assigned.

A later task may invert them:

```text
Codex
  ↓
Implementation
  ↓
Claude Code
  ↓
Review
```

The objective is not to determine a permanent "winner".

The objective is to learn which collaboration patterns produce the best results for Erick's working style.

Agents should provide concise explanations by default.

Detailed explanations should only be generated when requested.

---

# 15. Agent Authority

### Agents may independently

- inspect the repository;
- create and modify code;
- create tests;
- run tests;
- run linters/static analysis;
- analyze failures;
- create local commits when appropriate;
- propose architectural changes;
- review other agents' work.

### Human approval required for

- destructive operations;
- important architectural changes;
- production changes;
- operations involving real financial data;
- secret/credential changes;
- potentially irreversible database operations;
- GitHub push;
- merge.

Erick retains final authority.

---

# 16. Project Objective

The primary success criterion is not merely that the bot works.

The pilot must also provide evidence about:

- how Erick prefers to divide work between Codex and Claude Code;
- how agents should review each other;
- what information should be stored as project knowledge;
- how much context agents actually need;
- which documentation is useful versus unnecessary;
- how much autonomy agents should receive;
- how security reviews should be integrated;
- how a portable agent-development environment should eventually be structured.

The pilot is therefore both:

**a useful personal application**

and

**a laboratory for Erick's future AI-assisted engineering framework.**

---

# 17. Phase 1 Exit Criteria

Phase 1 is considered complete when:

- [x] Problem is defined.
- [x] Scope is defined.
- [x] Telegram is selected as interface.
- [x] n8n is selected as orchestrator.
- [x] Python is the deterministic business-logic layer.
- [x] Financial calculations are deterministic.
- [x] Transaction types are explicit.
- [x] Net balance semantics are defined.
- [x] Deterministic parser + LLM fallback is selected.
- [x] Append-only ledger is selected.
- [x] Event date and registration timestamp are required.
- [x] Correction strategy is conceptually defined.
- [x] Weekly and monthly reporting are defined.
- [x] Public-repository security requirements are defined.
- [x] Codex + Claude Code experimentation strategy is defined.
- [x] Human authority is established.

**Phase 1 status: APPROVED**

---

# 18. Phase 2 — Technical Design

The conceptual architecture above is the input to Phase 2.

Phase 2 must translate these decisions into an implementation-ready technical specification without introducing unnecessary functionality.