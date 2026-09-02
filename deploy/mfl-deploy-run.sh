#!/usr/bin/env bash
#
# mfl-deploy-run.sh -- the ONLY thing the CI deploy key may execute.
#
# Copy this to /usr/local/sbin/mfl-deploy-run.sh on the VPS, root:root, 0755
# (docs/block-8-cicd-deploy.md Part 3.2). It runs on the SYSTEM Docker daemon --
# the one that also runs gonex-postgres / gonex-n8n and owns `ledger-net` and
# `docker_gonex-network`. A separate rootless daemon cannot share those networks
# (B8-7), so the deploy has to use the system daemon; the isolation instead
# comes from: a forced `command=` on the key, this fixed reviewed script, and a
# sudoers rule scoped to this one path. `mfl-deploy` is NOT in the `docker`
# group and never touches the socket except through this script (run as root
# via that sudoers rule).
#
# Wiring (all applied by hand on the VPS -- Part 3):
#   /home/mfl-deploy/.ssh/authorized_keys :
#     command="sudo /usr/local/sbin/mfl-deploy-run.sh",restrict <the deploy pubkey>
#   /etc/sudoers.d/mfl-deploy :
#     Defaults:mfl-deploy !requiretty
#     Defaults!/usr/local/sbin/mfl-deploy-run.sh env_keep += "SSH_ORIGINAL_COMMAND"
#     mfl-deploy ALL=(root) NOPASSWD: /usr/local/sbin/mfl-deploy-run.sh
#
# The CI job runs:  ssh mfl-deploy@host "deploy <40-hex-git-sha>"
# which arrives here as $SSH_ORIGINAL_COMMAND. Anything else is refused.

set -euo pipefail

REPO_DIR=/home/mfl-deploy/deploy/monthly-financial-ledger
IMAGE_BASE=ghcr.io/erickdelpiero/monthly-financial-ledger

# --- validate the request ----------------------------------------------------
req="${SSH_ORIGINAL_COMMAND:-}"
read -r verb sha _rest <<<"$req" || true
[ "${verb:-}" = "deploy" ] \
  || { echo "refused: expected 'deploy <sha40>', got '${req}'" >&2; exit 2; }
[[ "${sha:-}" =~ ^[0-9a-f]{40}$ ]] \
  || { echo "refused: image sha is not 40 lowercase hex: '${sha:-}'" >&2; exit 2; }

IMAGE="${IMAGE_BASE}:${sha}"
export IMAGE

# --- refresh only the compose file from the public repo --------------------
# Run git as mfl-deploy so the checkout keeps its ownership (root would trip
# git's "dubious ownership" guard and rewrite file owners).
runuser -u mfl-deploy -- git -C "$REPO_DIR" fetch --quiet origin main
runuser -u mfl-deploy -- git -C "$REPO_DIR" checkout --quiet -B main origin/main
# Discard any local drift to a tracked file so the deploy always runs the
# committed compose.prod.yml exactly (B8-11 R5). Untracked files (./.env) are
# left alone.
runuser -u mfl-deploy -- git -C "$REPO_DIR" reset --hard --quiet origin/main

cd "$REPO_DIR"
CF=deploy/compose.prod.yml

# `docker compose -f <subdir>/file` takes the project directory from that
# subdir, so it would look for the .env in deploy/ and miss $REPO_DIR/.env.
# Point every invocation at the real env file explicitly.
DC=(docker compose --env-file "$REPO_DIR/.env" -f "$CF")

echo "==> pull ${IMAGE}"
docker pull "$IMAGE"

echo "==> migrate (alembic upgrade head as the schema-owner role; values from ${REPO_DIR}/.env)"
"${DC[@]}" run --rm migrate

echo "==> (re)create ledger-api"
# First pipeline run: this clears the Block-6 interim `docker run` container that
# still owns the name `ledger-api`. Afterwards it is a no-op compose would do
# itself; the ~2 s gap on a personal 2-user bot is acceptable.
docker rm -f ledger-api >/dev/null 2>&1 || true
"${DC[@]}" up -d api

echo "==> health gate"
ok=""
for _ in $(seq 1 30); do
  if "${DC[@]}" exec -T api python -c \
       "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3).status==200 else 1)"; then
    ok=1; break
  fi
  sleep 2
done
[ -n "$ok" ] || { "${DC[@]}" logs --tail 50 api; exit 1; }
echo "==> deployed ${IMAGE}"
