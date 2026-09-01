# Phase 2.2 — Repository Structure & Project Organization

**Project:** Personal Money Ledger Bot  
**Phase:** 2.2 — Technical Design  
**Status:** Final baseline after GPT + Claude review  
**Scope:** Repository organization only; implementation is deferred.

---

## 1. Purpose

Define a small, professional, portable repository structure for the pilot project without prematurely creating directories or files that have no current purpose.

The structure must support the current Telegram + n8n + Python + PostgreSQL project while remaining reusable as a pattern for future Python, ML/DL, NLP, CV, data analytics, API, and automation projects.

The repository will be public on GitHub.

---

## 2. Design Principles

1. **Minimal by default.** Add structure only when there is a real need.
2. **Professional and reusable.** Prefer conventions that scale to larger projects.
3. **Clear separation of concerns.** Source code, tests, documentation, agent instructions, CI/CD, and infrastructure have distinct homes.
4. **Public-repository safe by design.** Secrets and private runtime data must never be committed.
5. **Portable.** The repository can be used from Ubuntu and Windows without rebuilding the framework from scratch.
6. **Agent-friendly.** Codex and Claude Code can discover project rules and relevant knowledge without requiring a huge context file.
7. **Git-native.** Git/GitHub remains the source-control and versioning mechanism. The human owner performs push/merge operations.
8. **Evidence must be safe.** Intermediate or generated artifacts are never committed if they contain real financial or other private runtime data.

---

## 3. Proposed Repository Structure

```text
money-ledger/
├── .ai/
├── .github/
│   └── workflows/
├── docs/
├── scripts/
├── src/
│   └── money_ledger/
├── tests/
├── docker/
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── LICENSE
├── README.md
└── requirements.txt
```

The structure is intentionally small. Additional directories are introduced only when an actual requirement justifies them.

---

## 4. Directory and File Responsibilities

| Path | Purpose |
|---|---|
| `.ai/` | Project-specific AI knowledge, evidence, reviews, decisions, and supporting agent context. The exact internal structure will be designed later as part of the Project Knowledge System. |
| `.github/workflows/` | CI/CD automation and repository checks. |
| `docs/` | Human-facing project documentation: architecture, technical design, decisions, operations, etc. |
| `scripts/` | Small deterministic developer/operations scripts that do not belong in the application package. |
| `src/money_ledger/` | Application source code. Python follows the `src/` layout rather than placing the package directly at repository root. |
| `tests/` | Automated tests corresponding to application behavior. |
| `docker/` | Docker artifacts belonging specifically to this project. |
| `.env.example` | Safe template documenting required environment variables without containing real credentials. It must document the dedicated project database and least-privilege database credentials defined in Phase 2.1. |
| `.gitignore` | Prevents secrets, local environments, caches, generated/private runtime data, and real financial records from entering Git. |
| `AGENTS.md` | General instructions and operating rules for coding agents. |
| `CLAUDE.md` | Claude Code-specific instructions that complement, rather than duplicate, general agent rules. |
| `LICENSE` | Explicitly defines the repository's licensing terms. The exact license choice must be made before or at publication. |
| `README.md` | Public entry point explaining the project, purpose, setup, usage, architecture summary, and development workflow. |
| `requirements.txt` | Initial Python dependency specification, chosen for consistency with the user's existing projects and current workflow. |

---

## 5. Python Organization

The project will use the modern `src/` layout:

```text
src/
└── money_ledger/
    ├── ...
```

### Dependency-management decision

For this pilot, use **`requirements.txt`** rather than introducing `pyproject.toml` or a new package/dependency-management tool.

### Rationale

The user's existing Python projects already use:

- `requirements.txt`
- `venv` / `.venv`
- `pip`

No current requirement justifies introducing Poetry, uv, or another dependency-management workflow during this pilot.

This is intentionally a pragmatic decision rather than a claim that `requirements.txt` is universally superior.

A future framework revision may evaluate `pyproject.toml` and/or another modern Python tool once there is a demonstrated need across projects.

---

## 6. Infrastructure Organization

Infrastructure owned by this project will live inside the repository:

```text
docker/
.github/workflows/
scripts/
```

The repository will remain independent from the private GONEX infrastructure repository.

### Important boundary

The project **must not**:

- copy the private GONEX `.env`;
- commit GONEX credentials;
- depend on a private GONEX compose file being present in the repository;
- expose private infrastructure configuration through the public repository.

The production environment may connect to existing GONEX infrastructure (for example, the existing PostgreSQL/n8n deployment), but those connections must be represented through safe configuration and deployment mechanisms.

The exact Docker topology and deployment mechanism are deferred to the corresponding technical-design sections.

---

## 7. Database Configuration Boundary

Phase 2.1 established that the pilot should use a **dedicated database and dedicated least-privilege database role** inside the existing PostgreSQL instance if that infrastructure is confirmed suitable.

Therefore:

```text
.env.example
```

must document variables conceptually equivalent to:

```text
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
```

using placeholders/examples only.

The application must never rely on the PostgreSQL administrator credentials used by the existing infrastructure.

The exact variable names and PostgreSQL provisioning procedure belong to later technical-design sections.

---

## 8. Agent Organization

The project will initially expose:

```text
.ai/
AGENTS.md
CLAUDE.md
```

### Responsibility boundary

**`AGENTS.md`**
- General project rules.
- Human authority and approval requirements.
- Safe operating boundaries.
- Development/testing expectations.
- Rules applicable to coding agents generally.

**`CLAUDE.md`**
- Claude Code-specific operational guidance.
- References or complements `AGENTS.md`.
- Avoids unnecessary duplication.

**`.ai/`**
- Project Knowledge System.
- Curated project knowledge.
- Evidence and reviews from agents.
- Architectural decisions and relevant historical context.
- Future summaries/cleanup outputs.

The `.ai/` structure is intentionally **not fully defined in 2.2**. It will be designed after the repository baseline is established and after we observe how Codex and Claude Code actually work with the project.

---

## 9. Documentation Boundary

The project distinguishes between:

### `docs/`

Human-facing, durable project documentation.

Possible future organization:

```text
docs/
├── architecture/
├── technical-design/
├── decisions/
└── operations/
```

These subdirectories are **not required at repository creation time**.

### `.ai/`

Agent-oriented project knowledge, evidence, reviews, and context.

This prevents the public technical documentation from becoming a dumping ground for every intermediate agent interaction.

---

## 10. Git and Branching Policy

The project will use:

- Git
- GitHub
- `main` as the primary branch
- simple feature branches when parallel or isolated development is useful
- CI/CD through `.github/workflows/`

### Worktrees

**Git worktrees are deliberately deferred.**

They are not part of the initial operating model. They may be introduced later if the pilot demonstrates a genuine need for parallel isolated agent work.

This keeps the initial workflow aligned with the project's objective: learn how Codex + Claude Code should be used before adding more operational complexity.

---

## 11. Public Repository and Data-Safety Policy

This repository is intended to be public.

The following must **never** be committed:

- API keys
- passwords
- Telegram bot tokens
- database credentials
- private VPS credentials
- real financial records
- real transaction histories
- real screenshots of Yape/Plin payments
- private Telegram messages
- generated reports containing real financial data
- other private runtime data

### Important exception to an existing project pattern

`monthly-sop-automation` deliberately commits generated `output/` artifacts as evidence.

**That pattern does NOT apply here.**

For this project, evidence may be stored locally or in an appropriately controlled mechanism, but **real financial execution data must never be committed to the public repository**, even if it is considered "evidence."

Synthetic/mock data may be committed when needed for development, tests, examples, or demonstrations.

---

## 12. `.gitignore` Expectations

The initial `.gitignore` must cover at minimum:

```text
.env
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
n8n_data/
```

It must also prevent project-specific generated/private runtime data from entering Git.

The exact final `.gitignore` will be produced during implementation after the actual runtime directories are known.

---

## 13. Portability

The repository itself is the portable project unit.

The same repository should be usable on:

- Ubuntu
- Windows 11
- another Linux machine
- a future development environment

without depending on a machine-specific path such as:

```text
/home/erickdelpiero/Documents/Projects/
```

The portable unit consists of the project's source, tests, documentation, agent instructions, configuration templates, CI/CD configuration, and other version-controlled project artifacts.

Machine-specific secrets, credentials, and runtime state remain outside Git.

---

## 14. What Is Intentionally NOT Added Yet

To keep the pilot minimal, the initial repository will **not** create directories such as:

```text
data/
migrations/
prompts/
outputs/
config/
notebooks/
deploy/
```

unless a concrete requirement appears during implementation.

This is deliberate.

The framework should be discovered through actual use rather than designed around hypothetical future needs.

---

## 15. Current Repository Baseline

The user's existing projects show several useful patterns:

- `monthly-sop-automation` uses `src/` + `tests/` + `docs/` + `n8n/`.
- Python projects use `requirements.txt` + `venv`/`.venv`.
- `pangi-dev` separates workflows, prompts, and documentation.
- GitHub repositories use Git remotes and `main`.

For this pilot, the goal is not to reproduce any one existing repository, but to consolidate the strongest reusable conventions into a smaller, cleaner baseline.

The deliberate decisions for this pilot are:

- `src/` layout;
- `requirements.txt`;
- minimal initial repository;
- public-repository security;
- dedicated database credentials;
- separate agent/project knowledge boundaries;
- simple Git branching;
- worktrees deferred.

---

## 16. Open Questions Deferred to Later Technical Design

2.2 does **not** decide:

1. The internal `.ai/` Project Knowledge System structure.
2. Exact `AGENTS.md` and `CLAUDE.md` contents.
3. Docker Compose topology.
4. CI/CD implementation details.
5. Database migrations.
6. Telegram/n8n workflow structure.
7. Python package/module decomposition.
8. Testing strategy in detail.
9. Deployment directory/layout on the VPS.
10. Exact repository license selection.

Those decisions belong to later sections of Phase 2.

---

## 17. Decision Status

**FINAL — 2.2 Repository Structure & Project Organization**

This version incorporates the independent review from both GPT and Claude.

The repository structure is intentionally minimal. New components should be introduced only when justified by an actual project requirement.

**Next step:** Proceed to **2.3 — Data Model & Database Design**.
