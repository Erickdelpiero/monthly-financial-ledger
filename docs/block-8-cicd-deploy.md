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
| `deploy/compose.prod.yml` | repo | pulled onto the VPS; run by the wrapper |
| `deploy/mfl-deploy-run.sh` | repo | you copy to `/usr/local/sbin/` on the VPS (Part 3.2) |
| `n8n/workflow-reporte-{semanal,mensual}.json` | repo | you import + activate in n8n (Part 9) |
| `scripts/docker_smoke.sh` | repo | you run once on a Docker host (Part 7) |
| deploy user `mfl-deploy` + forced-command key + sudoers (A1) | VPS | you (Part 3) |
| deploy SSH key (private) | GitHub `production` env secret | you (Part 4) |
| `production` Environment + branch protection | GitHub settings | you (Part 4) |
| retire the interim `ledger-api` from Block 6 Step 3 | VPS (wrapper does it) | you verify (Part 8) |

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
- **A1 — deploy access:** the pipeline runs on the **system** Docker daemon
  (the only one that has `ledger-net` + the gonex DB network — B8-7). `mfl-deploy`
  is **not** in the `docker` group; its SSH key is locked to
  `command="sudo /usr/local/sbin/mfl-deploy-run.sh",restrict`, and a sudoers
  rule lets it run only that one root-owned script. See Part 3.

---

## Part 3 — Dedicated deploy user + forced-command wrapper (approach A1)

The pipeline's SSH key must **never** be your personal VPS key
(`gonex-pc-ubuntu` / `gonex-laptop-win11`).

**Why A1 (system daemon + forced command), not rootless:** `deploy/compose.prod.yml`
uses `ledger-net` and the DB network as `external`. Those exist only on the
**system Docker daemon** (the one running `gonex-postgres` / `gonex-n8n`). A
rootless daemon for `mfl-deploy` is a separate network namespace — it cannot
join those networks, so `ledger-api` there could not reach `gonex-postgres` and
`gonex-n8n` could not reach `ledger-api` (B8-7). So the deploy runs on the
system daemon, and the isolation comes from **three layers instead**: a forced
`command=` on the key, one fixed reviewed script (`deploy/mfl-deploy-run.sh`),
and a sudoers rule scoped to just that script. `mfl-deploy` is **not** in the
`docker` group and never touches the socket except through that script.

> The rootless Docker already installed for `mfl-deploy` is now **unused** —
> nothing in A1 talks to it. You can leave it installed (it is harmless and
> uses no resources while idle); there is no need to uninstall it. Just make
> sure the wrapper reaches the **system** daemon: `mfl-deploy` has no
> `DOCKER_HOST` set and is not in the `docker` group, so `docker` inside the
> root-run wrapper uses `/var/run/docker.sock` (the system daemon) — correct.

### 3.1 Generate the key (on your machine, not the VPS)

```
ssh-keygen -t ed25519 -N '' -C 'mfl-deploy-ci' -f ~/.ssh/mfl_deploy_ci
```
`~/.ssh/mfl_deploy_ci` (private) goes into GitHub Secrets; `.pub` goes on the VPS.

### 3.2 The deploy user, wrapper, sudoers rule, forced-command key

As root on the VPS:

```
# 1) the user -- real shell (a forced command= still runs via the user's shell,
#    so /usr/sbin/nologin would break it), password login disabled, NOT in the
#    docker group. If mfl-deploy already exists, just fix the shell / group:
id mfl-deploy >/dev/null 2>&1 || sudo adduser --disabled-password --gecos '' mfl-deploy
sudo usermod -s /bin/bash mfl-deploy
sudo gpasswd -d mfl-deploy docker 2>/dev/null || true
id mfl-deploy                                   # verify: no "docker" group
sudo -u mfl-deploy mkdir -p /home/mfl-deploy/.ssh /home/mfl-deploy/deploy
sudo chmod 700 /home/mfl-deploy/.ssh

# 2) the wrapper -- from this repo, root-owned, world-readable, NOT writable by
#    mfl-deploy. After the Block 8 commit is on `main`, either curl it:
sudo curl -fsSL \
  https://raw.githubusercontent.com/Erickdelpiero/monthly-financial-ledger/main/deploy/mfl-deploy-run.sh \
  -o /usr/local/sbin/mfl-deploy-run.sh
#    ...or, if you did 3.3 first, copy from the clone:
#  sudo install -m0755 -o root -g root \
#    /home/mfl-deploy/deploy/monthly-financial-ledger/deploy/mfl-deploy-run.sh \
#    /usr/local/sbin/mfl-deploy-run.sh
sudo chown root:root /usr/local/sbin/mfl-deploy-run.sh
sudo chmod 0755 /usr/local/sbin/mfl-deploy-run.sh
# sanity: the path in the script must match your clone location
grep -q '^REPO_DIR=/home/mfl-deploy/deploy/monthly-financial-ledger$' /usr/local/sbin/mfl-deploy-run.sh

# 3) sudoers -- mfl-deploy may run ONLY that script, as root, no password
sudo tee /etc/sudoers.d/mfl-deploy >/dev/null <<'EOF'
Defaults:mfl-deploy !requiretty
Defaults!/usr/local/sbin/mfl-deploy-run.sh env_keep += "SSH_ORIGINAL_COMMAND"
mfl-deploy ALL=(root) NOPASSWD: /usr/local/sbin/mfl-deploy-run.sh
EOF
sudo chmod 0440 /etc/sudoers.d/mfl-deploy
sudo visudo -c            # must print "parsed OK"
```

**The exact `authorized_keys` line.** Take the public key you generated in 3.1
(the single line `ssh-ed25519 AAAA…  mfl-deploy-ci`) and prepend the forced
command + `restrict`, on one line:

```
command="sudo /usr/local/sbin/mfl-deploy-run.sh",restrict ssh-ed25519 AAAA…YOUR_KEY_BODY…  mfl-deploy-ci
```

Install it (replace the `<<'EOF' … EOF` body with that full line):

```
sudo -u mfl-deploy tee /home/mfl-deploy/.ssh/authorized_keys >/dev/null <<'EOF'
command="sudo /usr/local/sbin/mfl-deploy-run.sh",restrict ssh-ed25519 AAAA…YOUR_KEY_BODY…  mfl-deploy-ci
EOF
sudo chmod 600 /home/mfl-deploy/.ssh/authorized_keys
```

`restrict` (OpenSSH ≥ 7.2) implies `no-pty,no-port-forwarding,no-agent-forwarding,
no-X11-forwarding,no-user-rc` and any future restrictions. If your sshd is
older, spell them out instead:
`command="sudo /usr/local/sbin/mfl-deploy-run.sh",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-user-rc ssh-ed25519 …`.

**No general `sudo`, no `docker` group.** `sudo -l -U mfl-deploy` must show only
`/usr/local/sbin/mfl-deploy-run.sh`; `id mfl-deploy` must not list `docker`.

### 3.3 Prepare the deploy directory (as `mfl-deploy`)

```
sudo -u mfl-deploy git clone \
  https://github.com/Erickdelpiero/monthly-financial-ledger.git \
  /home/mfl-deploy/deploy/monthly-financial-ledger
```
Only `deploy/compose.prod.yml` is used from this checkout; the wrapper keeps it
current (`git fetch` + `git checkout -B main origin/main`, run as `mfl-deploy`).
The wrapper looks for the repo at exactly
`/home/mfl-deploy/deploy/monthly-financial-ledger` — do not move it.

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

### 6.0a Diagnostic — evidence that rootless could not work (record, then move on)

Before applying A1, from the `mfl-deploy` account **as it is today** (rootless
daemon), capture:
```
sudo -u mfl-deploy env DOCKER_HOST=unix:///run/user/$(id -u mfl-deploy)/docker.sock docker ps
sudo -u mfl-deploy env DOCKER_HOST=unix:///run/user/$(id -u mfl-deploy)/docker.sock docker network ls
```
Expected: the rootless daemon shows **none of** `gonex-postgres` / `gonex-n8n`
and **no** `docker_gonex-network` / `ledger-net`. That is the concrete reason a
rootless deploy can't reach the DB or be reached by n8n (B8-7) — hence A1. Paste
this into the B8 close-out note.

### 6.0b Pre-flight (verify before you approve the first deploy)

**GitHub:**
- [ ] `production` environment exists with **you as required reviewer**, holds
      `DEPLOY_HOST`, `DEPLOY_USER` (= `mfl-deploy`), `DEPLOY_SSH_KEY`
      (Part 4.1-4.2).
- [ ] Branch protection on `main` (Part 4.3). The **CI / test** check only
      appears in that dropdown after `ci.yml` has run once — push the workflows
      first, let CI run, then add it.
- [ ] If the VPS SSH port is not 22: add `port: ${{ secrets.DEPLOY_PORT }}` to
      the `Deploy over SSH` step in `deploy.yml` + that secret.
- [ ] (optional hardening) pin `appleboy/ssh-action` to a commit SHA and pass
      the VPS host-key `fingerprint`.

**On the VPS, as your admin user (the SYSTEM daemon the wrapper will use):**
- [ ] `docker ps` lists `gonex-postgres` **and** `gonex-n8n`.
- [ ] `docker network ls` shows **both** `ledger-net` and the DB network
      (`docker_gonex-network` unless you set `LEDGER_DB_NETWORK`) — `compose`
      declares them `external` and fails fast if either is missing.
- [ ] `docker compose version` → **v2**; `command -v docker git runuser` all
      resolve (the wrapper runs via `sudo` with `secure_path`).
- [ ] `MIGRATE_DB_USER` (schema owner) can reach `gonex-postgres` from a
      container on the DB network — same path Block 6 Step 3 used for its
      one-off `alembic upgrade head`.

**A1 wiring (Part 3.2-3.4):**
- [ ] `sudo -l -U mfl-deploy` → **only** `/usr/local/sbin/mfl-deploy-run.sh`.
- [ ] `id mfl-deploy` → **no** `docker` group.
- [ ] `ls -l /usr/local/sbin/mfl-deploy-run.sh` → `-rwxr-xr-x root root` (not
      writable by `mfl-deploy`); `visudo -c` → parsed OK.
- [ ] `/home/mfl-deploy/.ssh/authorized_keys` starts with
      `command="sudo /usr/local/sbin/mfl-deploy-run.sh",restrict ` then your
      real pubkey; file `chmod 600`.
- [ ] `/home/mfl-deploy/deploy/monthly-financial-ledger` is a clean clone;
      `.../.env` exists, `chmod 600`, all six keys (Part 3.4).
- [ ] **End-to-end dry run** from your machine:
      `ssh -i ~/.ssh/mfl_deploy_ci mfl-deploy@<host> "help"` → refused with
      `expected 'deploy <sha40>'` (proves the forced command is active and
      rejects anything else). Then, with a real 40-hex commit sha already
      pushed to `main` and its image in GHCR (i.e. after the first pipeline
      build), `ssh -i ~/.ssh/mfl_deploy_ci mfl-deploy@<host> "deploy <sha>"`
      runs pull → migrate → up → health entirely.

### 6.1 Run it

1. Merge a trivial PR to `main` (or push a no-op commit).
2. Actions → the `Deploy` run → `deploy` job shows **"Waiting for review"** →
   approve it.
3. It builds + pushes the image, then SSHes `deploy <sha>` to the VPS. The
   forced-command wrapper (`/usr/local/sbin/mfl-deploy-run.sh`) validates the
   sha, `git fetch`es the compose file, `docker pull`s, runs
   `compose ... run --rm migrate`, then `compose ... up -d api` (force-removing
   the Block-6 interim container on this first run), then polls `/api/v1/health`.
   **On the very first run**, the wrapper fails at `docker pull` — do Part 5
   (make the package public) and *Re-run failed jobs*.
4. Verify from n8n (unchanged from Block 6):
   ```
   docker exec gonex-n8n sh -c 'wget -qO- http://ledger-api:8000/api/v1/health'
   ```
   → `{"status":"ok"}`.

Rollback: `git revert` the bad commit and push (the pipeline redeploys the
previous good state), or from your **admin** account on the VPS
`cd /home/mfl-deploy/deploy/monthly-financial-ledger && IMAGE=ghcr.io/erickdelpiero/monthly-financial-ledger:<older-sha> docker compose -f deploy/compose.prod.yml up -d api`
(`mfl-deploy` itself cannot run compose). A schema `alembic downgrade` is
**never** automatic (PHASE-2.7 §18 / §22).

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

## Part 8 — Confirm the interim `ledger-api` is gone (Block 6 Step 3)

The wrapper's first successful run already did `docker rm -f ledger-api` before
`compose up -d api`, so the bare interim container from Block 6 Step 3 is
replaced by the compose-managed one. Just verify (admin account):
```
docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' ledger-api
```
→ `money-ledger-prod` (not empty). The name (`ledger-api`) and networks
(`ledger-net`, the DB network) are unchanged, so workflows A/B and the
schedulers keep working. Re-check the n8n health probe from Part 6.1 step 4.

If for any reason the interim was created from a saved script/systemd unit,
disable that so it cannot recreate `ledger-api` on the next reboot.

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
| VPS user `mfl-deploy` (no `docker` group), forced-command `authorized_keys` | Part 3.2 | `sudo deluser --remove-home mfl-deploy` |
| `/usr/local/sbin/mfl-deploy-run.sh` + `/etc/sudoers.d/mfl-deploy` | Part 3.2 | `sudo rm` both |
| `/home/mfl-deploy/deploy/monthly-financial-ledger` checkout + `./.env` | Part 3.3-3.4 | `sudo rm -rf` the dir |
| GitHub env `production` (secrets + required reviewer) | Part 4 | delete the environment |
| Branch protection on `main` | Part 4.3 | delete the rule |
| GHCR package made public | Part 5 | set visibility back to private |
| First pipeline deploy (image + container) | Part 6 | `git revert` + push, or admin `compose up -d api` with an older tag |
| Interim `ledger-api` replaced by compose-managed | Part 6 wrapper / Part 8 | admin: `docker rm -f ledger-api` + old `docker run` from Block 6 Step 3 |
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
- **Deploy-access hardening** — resolved as **A1** (Part 3: system daemon,
  forced-command wrapper, scoped sudoers, no `docker` group). The rootless
  daemon installed earlier for `mfl-deploy` is now unused; leave it, no need to
  uninstall. Revisit A1 only if more people get deploy access.
