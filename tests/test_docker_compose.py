"""Full local stack via docker compose (PHASE-2.9 §14). Skipped without Docker.

Brings up db -> migrate -> api with a password full of URL-reserved characters
(the Block-5-review concern), then checks health, non-root, and that the
migration reached head. Automates what scripts/docker_smoke.sh does by hand.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT = "ml_compose_pytest"

# Deliberately nasty: @ : / # % and a space.
NASTY_PASSWORD = "p@ss:w/rd#1%2 x"

ENV = {
    **os.environ,
    "COMPOSE_PROJECT_NAME": PROJECT,
    "POSTGRES_PASSWORD": NASTY_PASSWORD,
    "API_INTERNAL_TOKEN": "compose-pytest-token",
    "DB_HOST_PORT": "55432",
    "API_HOST_PORT": "58000",
}


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=15, check=True)
        return True
    except Exception:
        return False


def _compose(*args: str, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        env=ENV,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def stack():
    if not _docker_ok():
        pytest.skip("docker daemon is not available")
    # No .env needed: ENV below supplies every required variable, so a clean CI
    # checkout still runs this test.
    _compose("down", "-v", "--remove-orphans", check=False)
    try:
        _compose("up", "-d", "--build", timeout=900)
        yield
    finally:
        _compose("down", "-v", "--remove-orphans", check=False)


def _api_health_status() -> str:
    cid = _compose("ps", "-q", "api").stdout.strip()
    if not cid:
        return "gone"
    return subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", cid],
        capture_output=True, text=True, check=False,
    ).stdout.strip()


def test_stack_starts_healthy_migrated_and_non_root(stack) -> None:
    status = "starting"
    for _ in range(60):
        status = _api_health_status()
        if status == "healthy":
            break
        if status in ("unhealthy", "gone"):
            logs = _compose("logs", check=False).stdout
            pytest.fail(f"api status={status}\n{logs[-4000:]}")
        time.sleep(2)
    assert status == "healthy", f"api never became healthy (last: {status})"

    uid = _compose("exec", "-T", "api", "id", "-u").stdout.strip()
    assert uid != "0" and int(uid) >= 10000

    current = _compose("exec", "-T", "api", "alembic", "current").stdout
    assert "0002_append_only_delete_guard" in current

    # the app itself can reach the DB (proves the URL-encoded password works)
    _compose(
        "exec", "-T", "api", "python", "-c",
        "import urllib.request,sys;"
        "sys.exit(0 if urllib.request.urlopen("
        "'http://127.0.0.1:8000/api/v1/health').status==200 else 1)",
    )
