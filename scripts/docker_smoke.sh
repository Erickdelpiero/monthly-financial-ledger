#!/usr/bin/env bash
# Local end-to-end check of the container + compose stack (PHASE-2.9 §14).
# Builds the image, brings up db -> migrate (one-shot) -> api, verifies health
# and that the API process is non-root, then tears everything down.
#
#   scripts/docker_smoke.sh
#
# Compose reads .env itself; this script never sources it.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Create .env from .env.example first."; exit 1; }

cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> build"
docker compose build

echo "==> up (db -> migrate -> api)"
docker compose up -d

cid="$(docker compose ps -q api)"
echo "==> wait for api health"
status=starting
for _ in $(seq 1 40); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)"
  [ "$status" = healthy ] && break
  [ "$status" = unhealthy ] && { docker compose logs api; exit 1; }
  sleep 2
done
[ "$status" = healthy ] || { echo "api never became healthy ($status)"; docker compose logs; exit 1; }

# Ask compose which host address it actually published (no .env parsing).
addr="$(docker compose port api 8000)"
echo "==> GET http://${addr}/api/v1/health"
curl -fsS "http://${addr}/api/v1/health"; echo

echo "==> non-root check"
uid="$(docker compose exec -T api id -u | tr -d '[:space:]')"
echo "api uid = ${uid}"
[ "${uid}" != "0" ] || { echo "FAIL: api runs as root"; exit 1; }

echo "==> migration is at head"
docker compose exec -T api alembic current

# The monthly-report PNG path exercises matplotlib inside the runtime image
# (Block 7 / B8). Runs in-container: no host curl, no .env parsing -- the token
# is read from the container's own environment. Reports on the month that just
# ended (B8-11 R6) rather than a fixed date, so the query stays meaningful over
# time; an empty month still renders a valid PNG, so the check holds either way.
echo "==> GET /api/v1/reports/monthly/image (matplotlib render)"
docker compose exec -T api python -c "
import urllib.request, os, sys, datetime
first = datetime.date.today().replace(day=1)
prev = first - datetime.timedelta(days=1)
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/reports/monthly/image?year=%d&month=%d' % (prev.year, prev.month),
    headers={'X-API-Key': os.environ['API_INTERNAL_TOKEN']},
)
body = urllib.request.urlopen(req, timeout=10).read()
sys.exit(0 if body[:8] == b'\x89PNG\r\n\x1a\n' else 1)
" && echo "   monthly PNG OK" || { echo "FAIL: monthly image is not a valid PNG"; exit 1; }

echo "OK"
