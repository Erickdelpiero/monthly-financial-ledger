# Block 8 — CI/CD, production deploy, report schedulers

**Status:** repo side implemented (workflows, prod compose, scheduler exports,
smoke check). **Nothing on the VPS or in GitHub settings has been changed by an
agent** — Parts 3–10 are the manual runbook for Erick, same pattern as
`docs/block-6-n8n-telegram.md`.

Reference: PHASE-2.7 §23-28 / §37-39, PHASE-2.11 §2.1 / §4.3 / §8, PHASE-2.12 §4.

---

## Part 1 — What is automated vs manual

| Piece | Where | Who applies it |
|---|---|---|
| `.github/workflows/ci.yml` | repo | runs on every PR + push to `main` |
| `.github/workflows/deploy.yml` | repo | runs on push to `main`, **after CI green + your approval** |
| `deploy/compose.prod.yml` | repo | pulled onto the VPS; run by the pipeline |
| `n8n/workflow-reporte-{semanal,mensual}.json` | repo | you import + activate in n8n (Part 10) |
| `scripts/docker_smoke.sh` | repo | you run once on a Docker host (Part 8) |
| dedicated deploy SSH key + user | VPS + GitHub Secrets | you (Part 3) |
| `production` Environment + branch protection | GitHub settings | you (Part 4) |
| retire the interim `ledger-api` from Block 6 Step 3 | VPS | you (Part 9) |

---

## Part 2 — Decisions (confirmed with Erick)

- **A — image delivery:** GHCR (`ghcr.io/erickdelpiero/monthly-financial-ledger`).
  The runner pushes with the built-in `GITHUB_TOKEN`; the VPS pulls. Public repo
  → make the package **public** (Part 6) so the VPS needs no registry login.
- **B — deploy gate:** a GitHub **Environment `production` with a required
  reviewer (you)**. Every deploy pauses for your click. This is also the
  human-approval gate for a potentially destructive migration (PHASE-2.7 §27).
- **C — migrations:** the pipeline runs `alembic upgrade head` for **additive**
  migrations as a deliberate step, as the **schema-owner role** (not
  `money_ledger_app`), using values from the VPS `./.env`. A destructive
  migration must not be pushed to `main` without being applied/approved
  out of band first.
- **D — schedulers:** weekly text **Sunday 19:00 America/Lima**
  (`0 19 * * 0`); monthly PNG **day 1, 07:00 America/Lima** (`0 7 1 * *`),
  reporting on the month that just ended. Both go to every id in
  `TELEGRAM_AUTHORIZED_IDS`.
- **E — lint:** light only (compile + import-graph check) in CI; no `ruff` yet.
- **F — workflow:** branch protection on `main` → changes land via feature
  branch + PR from now on (PHASE-2.7 §26).

---

## Part 3 — Dedicated deploy SSH key + user (PHASE-2.11 §4.3)

The pipeline's SSH key must **never** be your personal VPS key
(`gonex-pc-ubuntu` / `gonex-laptop-win11`). Create a fresh one, scoped to this
project's deploy.

### 3.1 Generate the key (on your machine, not the VPS)

```
ssh-keygen -t ed25519 -N '' -C 'mfl-deploy-ci' -f ~/.ssh/mfl_deploy_ci
```
`~/.ssh/mfl_deploy_ci` (private) goes into GitHub Secrets; `.pub` goes on the VPS.

### 3.2 A dedicated, low-privilege deploy user on the VPS

```
sudo adduser --disabled-password --gecos '' mfl-deploy
sudo mkdir -p /home/mfl-deploy/.ssh
sudo tee /home/mfl-deploy/.ssh/authorized_keys < ~/.ssh/mfl_deploy_ci.pub
sudo chown -R mfl-deploy:mfl-deploy /home/mfl-deploy/.ssh
sudo chmod 700 /home/mfl-deploy/.ssh && sudo chmod 600 /home/mfl-deploy/.ssh/authorized_keys
```

Docker access is the sensitive part (PHASE-2.7 §25, risk R2 — membership of the
`docker` group ≈ root on the host). Two acceptable options; pick one:

1. **Rootless Docker for `mfl-deploy`** (preferred): install rootless Docker for
   that user only. The pipeline then talks to that user's own daemon; a
   compromised key cannot touch the host's root Docker.
2. **`docker` group membership** (simpler, weaker): `sudo usermod -aG docker
   mfl-deploy`. Accept that this is high privilege and rely on the key being
   CI-only and the `production` approval gate.

Do **not** grant general `sudo`.

### 3.3 Prepare the deploy directory

As `mfl-deploy`:
```
cd ~ && mkdir -p deploy && cd deploy
git clone https://github.com/Erickdelpiero/monthly-financial-ledger.git
cd monthly-financial-ledger
```
Only `deploy/compose.prod.yml` is used from this checkout; the pipeline keeps it
current with `git fetch` + `git checkout -B main origin/main`.

### 3.4 The production `./.env` (git-ignored, never committed)

In `~/deploy/monthly-financial-ledger/.env`:
```
DB_NAME=personal_finance_bot
DB_USER=money_ledger_app
DB_PASSWORD=<the app-role password from Block 6 Step 2>
MIGRATE_DB_USER=<the schema-owner / admin role>
MIGRATE_DB_PASSWORD=<its password>
API_INTERNAL_TOKEN=<the same value n8n's Header Auth credential uses>
# optional, defaults shown:
# DB_HOST=gonex-postgres
# DB_PORT=5432
# LEDGER_DB_NETWORK=docker_gonex-network
```
`chmod 600 .env`. `.env` is matched by the repo's `.gitignore`, so a stray
`git add -A` in this dir cannot stage it — but never commit from here anyway.

---

## Part 4 — GitHub settings

### 4.1 Secrets (Settings → Secrets and variables → Actions → **Environment
secrets** of a new environment `production`)

| Name | Value |
|---|---|
| `DEPLOY_HOST` | the VPS host/IP |
| `DEPLOY_USER` | `mfl-deploy` |
| `DEPLOY_SSH_KEY` | contents of `~/.ssh/mfl_deploy_ci` (the **private** key) |

No DB or API secrets in GitHub — those live only in the VPS `./.env`
(PHASE-2.7 §28).

### 4.2 The `production` environment

Settings → Environments → **New environment** → `production`:
- **Required reviewers:** add yourself. Now every `deploy` job waits for your
  approval in the Actions run.
- (optional) restrict deployment branches to `main`.

### 4.3 Branch protection on `main`

Settings → Branches → add rule for `main`:
- Require a pull request before merging.
- Require status checks to pass → select the **CI / test** check.
- (optional) Require branches to be up to date before merging.

From here: work on a feature branch, open a PR, CI runs; merge to `main`
triggers `deploy.yml`.

---

## Part 5 — GHCR package visibility (a deliberate chicken-and-egg)

`deploy.yml` declares `permissions: packages: write`, so the built-in
`GITHUB_TOKEN` can push the image — **no PAT or extra secret is needed to
push**. But a newly created GHCR package is **private by default**, even from a
public repo, and the VPS `docker pull` in the SSH step has no registry login.
So the very first `deploy` run goes like this:

1. `Build and push image` **succeeds** and creates the (private) package
   `ghcr.io/erickdelpiero/monthly-financial-ledger`.
2. `Deploy over SSH` **fails** at `docker pull` (`denied` / `not found`) —
   expected, the package is still private.
3. GitHub → your profile → **Packages** → `monthly-financial-ledger` →
   *Package settings* → **Change visibility → Public**. (While there, confirm
   *Manage Actions access* lists this repo with **Write** — it is linked
   automatically on first push.)
4. Re-run the failed `deploy` job (Actions → the run → *Re-run failed jobs*).
   `docker pull` now works without any login.

Every later deploy just works — the package stays public.

---

## Part 6 — First deploy

### 6.0 Pre-flight (verify before you approve the first deploy)

- [ ] GitHub → the `production` environment exists with **you as required
      reviewer**, and holds `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
      (Part 4.1-4.2).
- [ ] Branch protection on `main` is on (Part 4.3). Note: the **CI / test**
      status check only appears in that dropdown after `ci.yml` has run once —
      push the workflows first, let CI run, then add it to the rule.
- [ ] On the VPS as `mfl-deploy`: `ssh mfl-deploy@<host>` works with the new
      key; `docker compose version` shows **v2**; `git --version` present;
      `~/deploy/monthly-financial-ledger` is a clean clone (Part 3.3);
      `~/deploy/monthly-financial-ledger/.env` exists, `chmod 600`, with all
      six required keys (Part 3.4).
- [ ] `docker network ls` shows **both** `ledger-net` and the DB network
      (`docker_gonex-network` unless you set `LEDGER_DB_NETWORK`). `compose`
      declares them `external` and fails fast if either is missing.
- [ ] `MIGRATE_DB_USER` (schema owner) can reach `gonex-postgres` from a
      container on the DB network — this is the same path Block 6 Step 3 used
      for its one-off `alembic upgrade head`, so it should already work.
- [ ] If the VPS SSH port is not 22: add `port: ${{ secrets.DEPLOY_PORT }}` to
      the `Deploy over SSH` step in `deploy.yml` and add that secret.
- [ ] (optional hardening) pin `appleboy/ssh-action` to a commit SHA and pass
      the VPS host-key `fingerprint`.

### 6.1 Run it

1. Merge a trivial PR to `main` (or push a no-op commit).
2. Actions → the `Deploy` run → `deploy` job shows **"Waiting for review"** →
   approve it.
3. It builds + pushes the image, SSHes to the VPS, runs
   `docker compose -f deploy/compose.prod.yml run --rm migrate`, then
   `... up -d api`, then polls `/api/v1/health`.
   **On the very first run**, the SSH step fails at `docker pull` — do Part 5
   (make the package public) and *Re-run failed jobs*.
4. Verify from n8n (unchanged from Block 6):
   ```
   docker exec gonex-n8n sh -c 'wget -qO- http://ledger-api:8000/api/v1/health'
   ```
   → `{"status":"ok"}`.

Rollback: re-run the pipeline pinned to a previous image, or on the VPS
`IMAGE=ghcr.io/erickdelpiero/monthly-financial-ledger:<older-sha> docker compose
-f deploy/compose.prod.yml up -d api`. A schema `alembic downgrade` is **never**
automatic (PHASE-2.7 §18 / §22).

---

## Part 7 — Docker smoke with the matplotlib image (prerequisite C5-4)

On any machine with a Docker daemon and a local `.env`
(from `.env.example`):
```
scripts/docker_smoke.sh
```
It now also asserts `GET /api/v1/reports/monthly/image` returns real PNG bytes,
i.e. matplotlib works inside the runtime image. Confirm: image builds, `migrate`
reaches `0002 (head)`, `api` becomes `healthy`, `id -u` ≠ 0, monthly PNG OK,
`down -v` cleans up.

---

## Part 8 — Retire the interim `ledger-api` (Block 6 Step 3)

Only after Part 6 is green and n8n reaches the pipeline-managed container:
```
# the interim container was started with a bare `docker run --name ledger-api ...`
docker rm -f ledger-api          # the pipeline's `compose ... up -d api` already
                                 # owns the name now; if both ever exist, stop the
                                 # bare one and let compose recreate it
docker compose -f ~/deploy/monthly-financial-ledger/deploy/compose.prod.yml up -d api
```
Then re-check the n8n health probe. The container name (`ledger-api`) and the
networks (`ledger-net`, the DB network) are unchanged, so workflows A/B and the
schedulers keep working.

Rollback: `docker rm -f ledger-api` then re-run the old `docker run` from
Block 6 Step 3.

---

## Part 9 — Import + activate the report schedulers

In n8n (Import from File):
- `n8n/workflow-reporte-semanal.json` — Schedule `0 19 * * 0`, GET
  `/api/v1/reports/weekly`, `sendMessage` to each `TELEGRAM_AUTHORIZED_IDS`.
- `n8n/workflow-reporte-mensual.json` — Schedule `0 7 1 * *`, GET
  `/api/v1/reports/monthly/image` for the previous month, `sendPhoto`.

Both reuse the existing credentials by name (`Header Auth account-CuentasDN`,
`Telegram account-CuentasDN`) and `$env.TELEGRAM_AUTHORIZED_IDS` (already set,
with `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` from B6-9). Confirm the credential
dropdowns after import.

They use a **Schedule Trigger**, not a Telegram Trigger, so there is no webhook
conflict with workflow A — activate both.

**Verify:** open each workflow → *Execute Workflow* (manual run) → both chats
receive the weekly text / the monthly PNG. Then leave them active.

Rollback: deactivate / delete the two workflows.

---

## Part 10 — Change & rollback register

| Change | Applied by | Rollback |
|---|---|---|
| Deploy SSH keypair `mfl_deploy_ci` | Part 3.1 | delete the key files |
| VPS user `mfl-deploy` + `authorized_keys` + Docker access | Part 3.2 | `sudo deluser --remove-home mfl-deploy` |
| `~/deploy/monthly-financial-ledger` checkout + `./.env` | Part 3.3-3.4 | `rm -rf` the dir |
| GitHub env `production` (secrets + required reviewer) | Part 4 | delete the environment |
| Branch protection on `main` | Part 4.3 | delete the rule |
| GHCR package made public | Part 5 | set visibility back to private |
| First pipeline deploy (image + container) | Part 6 | previous image tag, `compose up -d api` |
| Interim `ledger-api` retired | Part 8 | old `docker run` from Block 6 Step 3 |
| 2 scheduler workflows imported + active | Part 9 | deactivate / delete |

Nothing is applied until this register + Parts 3–10 are reviewed.

---

## Part 11 — Still open / not in this block

- **Backblaze B2 encryption** and the **backup cron `PATH`** fix
  (`b2: command not found`) — inherited `gonex-infra` debt (PHASE-2.11 §2.2 /
  §8), must be resolved before this project's DB relies on that backup, but not
  a Block 8 deliverable.
- **Backup restore drill** for `personal_finance_bot` (PHASE-2.7 §35) — do once
  before calling production mature.
- **Block 6 deferred E2E** (B6-9): notification, `/corregir`,
  no-cross-correction, netting.
- **Exact Docker-access hardening** for `mfl-deploy` (rootless vs `docker`
  group) — decided in Part 3.2; revisit if more people get deploy access.
