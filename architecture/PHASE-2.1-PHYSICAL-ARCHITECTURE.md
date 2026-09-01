# Phase 2.1 — Physical Architecture

**Project:** Personal Finance Flow Bot  
**Phase:** 2 — Technical Design  
**Section:** 2.1 — Physical Architecture  
**Status:** Final — Agreed Baseline  
**Version:** 1.1

---

## 1. Objective

Define where each component of the system will run and how the development, deployment, and production environments will interact.

The architecture must:

- preserve local-first development;
- reuse the existing VPS infrastructure where appropriate;
- minimize unnecessary infrastructure;
- maintain a clear separation between development and production;
- support Git/GitHub and CI/CD;
- remain portable enough to reproduce the development environment on another machine.

---

## 2. Existing Infrastructure

The production VPS is an **Ubuntu 24.04.4 LTS** server hosted by Contabo.

Verified resources:

- 6 vCPUs
- ~11 GB RAM
- ~96 GB disk
- ~61 GB available at verification time
- Docker 29.3.0
- Docker Compose v5.1.1
- Nginx present
- SSH access available
- PostgreSQL runs in Docker
- n8n runs in Docker
- Redis runs in Docker

The existing infrastructure is containerized and should be reused rather than duplicated.

---

## 3. Existing Docker Infrastructure

Relevant existing containers:

| Component | Container | Image |
|---|---|---|
| n8n | `gonex-n8n` | `n8nio/n8n:latest` |
| PostgreSQL | `gonex-postgres` | `postgres:16` |
| Redis | `gonex-redis` | `redis:7-alpine` |
| ThingsBoard | `gonex-thingsboard` | `thingsboard/tb-pe-node:4.3.0PE` |
| ThingsBoard Web Report | `gonex-tb-web-report` | `thingsboard/tb-pe-web-report:4.3.0PE` |
| Evolution API | `gonex-evolution` | `evoapicloud/evolution-api:latest` |
| Mosquitto | `gonex-mosquitto` | `eclipse-mosquitto:2` |

For this project, the relevant existing services are primarily:

```text
gonex-n8n
gonex-postgres
gonex-redis
```

---

## 4. Existing Docker Network

The current relevant containers are connected to:

```text
docker_gonex-network
```

This is a Docker bridge network currently shared by multiple GONEX services.

This network **must not automatically be treated as the project's security boundary**.

The new backend may need controlled access to PostgreSQL and/or n8n, but the detailed Docker/network design must evaluate whether a more isolated network arrangement is preferable.

The project should not unnecessarily gain network reachability to unrelated GONEX services.

---

## 5. Production Architecture

The target production topology is:

```text
                         INTERNET
                            │
                            ▼
                    ┌────────────────┐
                    │    Telegram    │
                    └───────┬────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │      n8n       │
                    │  Orchestrator  │
                    └───────┬────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │ Python Backend │
                    │ Business Logic │
                    └───────┬────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │  PostgreSQL 16 │
                    │  Project DB    │
                    └────────────────┘

              Nginx / HTTPS enters the architecture
              only where technically required.
```

The exact Telegram transport mechanism (webhook vs. polling) remains to be determined in the Telegram/n8n technical design.

Therefore, Nginx is **not assumed to be in the Telegram critical path** until that decision is made.

---

## 6. Component Responsibilities

### Telegram

Responsible for:

- user interaction;
- buttons;
- transaction input;
- displaying deterministic responses;
- receiving reports.

Telegram does not contain financial business logic.

### n8n

Responsible for:

- Telegram integration;
- workflow orchestration;
- scheduled weekly execution;
- scheduled monthly execution;
- invoking the Python backend;
- delivering messages/reports.

n8n is not the financial calculation engine.

### Python Backend

Responsible for:

- business rules;
- deterministic parsing;
- validation;
- financial calculations;
- ledger operations;
- correction logic;
- report data generation;
- controlled LLM fallback integration.

Python is the authoritative implementation of financial-domain logic.

### PostgreSQL

Responsible for:

- persistent storage;
- transaction history;
- auditability;
- ledger state derived from events.

PostgreSQL is the financial source of truth.

### Nginx

Responsible for:

- HTTPS;
- reverse proxying;
- routing external HTTP(S) traffic where required.

Its exact role is deferred until the transport/API design is defined.

---

## 7. Dedicated Database and Database Role

The project will use the existing PostgreSQL 16 **instance**, but it will not share the existing n8n/GONEX application database namespace.

A dedicated database must be created for this project, for example:

```text
personal_finance_bot
```

A dedicated PostgreSQL role/user must also be created, for example:

```text
personal_finance_bot
```

The application must connect using this dedicated role with **least privilege**.

The application must never use:

- PostgreSQL superuser credentials;
- n8n's database credentials;
- GONEX administrative credentials.

The exact database name, role name, grants, migrations, and credential management belong to the database/infrastructure design sections.

This isolation is a hard architectural requirement.

---

## 8. Repository and Docker Compose Isolation

The project will have its **own public GitHub repository** and its own project-level Docker configuration.

The project's Docker Compose configuration must be self-contained and must not depend on:

```text
~/gonex/docker/.env
```

or other private GONEX configuration files.

The project may connect to existing infrastructure through explicitly documented interfaces or Docker networks, but its source repository must remain independently reproducible.

No private GONEX secrets, credentials, or configuration should be required to understand or build the project.

The exact Docker/network integration mechanism belongs to the detailed infrastructure design.

---

## 9. Development Environment

Primary development environment:

```text
Ubuntu PC

/home/erickdelpiero/Documents/Projects/
```

The project will be maintained as a normal Git repository.

Development flow:

```text
Ubuntu
   │
   ├── Local development
   ├── Tests
   └── Git
        │
        ▼
      GitHub
        │
        ▼
       CI/CD
        │
        ▼
       VPS
        │
        ▼
    Production
```

Local development must not depend on production data.

---

## 10. Local vs. Production

### Local Ubuntu

Expected to run:

- Python backend;
- automated tests;
- parser;
- business logic;
- development tooling.

A development PostgreSQL environment will be defined in the database/infrastructure sections.

### VPS

Expected to run:

- n8n;
- production PostgreSQL;
- production backend;
- Nginx where required;
- production integrations.

The exact deployment mechanism will be defined later.

---

## 11. Database Strategy

PostgreSQL is the selected database technology for production and development whenever practical.

Reasons:

- PostgreSQL 16 already exists in the VPS;
- production and development can use the same database technology;
- avoiding an SQLite-to-PostgreSQL migration reduces unnecessary complexity;
- PostgreSQL provides appropriate transactional and constraint capabilities for a financial ledger.

Production data and credentials must never be used directly by local development.

---

## 12. Telegram Transport

The architecture intentionally does **not** assume webhook or polling yet.

Two options will be evaluated in the Telegram/n8n design:

### Polling

```text
n8n → Telegram API
```

Advantages:

- no public webhook endpoint required for Telegram;
- simpler network exposure.

### Webhook

```text
Telegram
   │
 HTTPS
   ▼
Nginx / n8n
```

Advantages:

- event-driven delivery;
- potentially cleaner production integration.

The final choice must be based on the actual n8n/Telegram configuration and operational requirements.

---

## 13. Network Security

PostgreSQL must not be publicly exposed merely for convenience.

Preferred principle:

```text
Application
    │
    ▼
Controlled internal Docker connectivity
    │
    ▼
PostgreSQL
```

rather than:

```text
Internet
    │
    ▼
PostgreSQL :5432
```

Because `docker_gonex-network` is shared with unrelated services, the detailed network design must explicitly minimize the backend's reachability.

---

## 14. Deployment Strategy

The intended deployment direction is:

```text
Developer
   │
   ▼
Git commit
   │
   ▼
GitHub
   │
   ▼
CI
 ├── tests
 ├── lint/static analysis
 └── security checks
   │
   ▼
CD
   │
   ▼
VPS
   │
   ▼
Docker deployment
```

The exact CI/CD implementation is deferred to the dedicated CI/CD design.

GitHub push/merge remains human-controlled.

---

## 15. Portability Requirement

The development environment must eventually be reproducible on another machine, including the Windows 11 laptop if hardware requirements make it preferable.

The repository should minimize dependence on:

- absolute machine-specific paths;
- undocumented system packages;
- manually configured hidden state;
- local-only configuration;
- machine-specific credentials.

The final portability mechanism may use:

- Docker;
- Dev Containers;
- setup scripts;
- environment templates;
- or a combination.

The simplest solution that satisfies reproducibility should be preferred.

---

## 16. Production Safety

Agents may perform normal development operations within the project.

The following require explicit human approval:

- destructive production database operations;
- destructive migrations;
- production infrastructure changes;
- credential/secret changes;
- irreversible operations;
- production deployment when the deployment mechanism could cause destructive impact.

The project must favor reversible operations and maintain Git-based recovery.

---

## 17. Existing Backup Infrastructure

The VPS already contains:

```text
~/gonex/docker/backup.sh
~/gonex/docker/backup.log
```

This existing backup mechanism must be inspected during the backup/restore design before creating a second independent backup strategy.

The final design must explicitly determine whether the dedicated project database is covered by the existing backup process and, if not, how it will be included.

---

## 18. Open Questions for Subsequent Sections

The following are intentionally deferred:

1. Exact development PostgreSQL strategy.
2. Exact Docker Compose structure.
3. Docker network isolation strategy.
4. Telegram polling vs. webhook.
5. Local interaction with the production n8n workflow, if needed.
6. Backend API protocol and contract.
7. Backend VPS deployment mechanism.
8. Nginx routing.
9. CI/CD implementation.
10. Database migration strategy.
11. Backup and restore implementation.
12. Rollback strategy.

These are detailed-design questions, not unresolved blockers for the physical architecture.

---

## 19. Architectural Decisions — Final Baseline

The following decisions are considered established for the remainder of Phase 2 unless new evidence justifies reopening them:

- Local-first development on Ubuntu.
- Git/GitHub as source control.
- CI/CD as the deployment direction.
- Existing VPS infrastructure will be reused.
- n8n remains the production orchestrator.
- Python remains the authoritative business-logic layer.
- PostgreSQL 16 remains the database technology.
- The project receives its own dedicated PostgreSQL database.
- The project receives its own least-privilege PostgreSQL role.
- PostgreSQL will not be publicly exposed.
- The project has its own public repository.
- The project has independent Docker configuration.
- The project must not depend on private GONEX `.env` files.
- Network access to unrelated GONEX services must be minimized.
- Telegram transport remains open until technical evaluation.
- Production operations with destructive or irreversible impact require human approval.
- Existing backup infrastructure will be evaluated before introducing another backup mechanism.
- Portability is a first-class requirement.

---

## 20. Phase 2.1 Exit Criteria

- [x] VPS infrastructure inspected.
- [x] Docker architecture inspected.
- [x] n8n identified.
- [x] PostgreSQL identified.
- [x] Redis identified.
- [x] Docker network identified.
- [x] Local development environment identified.
- [x] Production responsibilities defined.
- [x] Local/production separation established.
- [x] PostgreSQL selected.
- [x] Dedicated project database requirement established.
- [x] Dedicated least-privilege database role established.
- [x] Public PostgreSQL exposure prohibited.
- [x] Repository isolation established.
- [x] Private GONEX configuration dependency prohibited.
- [x] Network isolation requirement established.
- [x] Telegram transport explicitly deferred for technical evaluation.
- [x] GitHub + CI/CD established as deployment direction.
- [x] Production safety principles established.
- [x] Portability established as a requirement.
- [x] Existing backup mechanism identified for later evaluation.

**Status: FINAL — READY FOR PHASE 2.2**
