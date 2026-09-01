# syntax=docker/dockerfile:1
#
# Backend image for the Personal Expense Ledger API (PHASE-2.7 §3-4, §14-16).
# - multi-stage: build deps into a venv, ship a slim runtime
# - runs as a non-root user (PHASE-2.9 §14.2)
# - no secrets baked in; configuration comes from the environment (PHASE-2.7 §12)

FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src

# Dedicated non-root account with a fixed high UID.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations/ ./migrations/
COPY --chown=app:app src/ ./src/

USER app

# Documentation only: this port is published (loopback) by compose in dev and
# reached over the internal network by n8n in production. Never internet-facing.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"]

# Alembic migrations are run as a deliberate step (compose `migrate` service /
# CI), not from this entrypoint (PHASE-2.7 §17).
CMD ["uvicorn", "--factory", "money_ledger.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
