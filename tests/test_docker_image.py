"""Container image checks (PHASE-2.9 §14). Skipped when no Docker daemon.

These build the real image and inspect it; they do not need a database. The
full compose flow (health, migrations) is `test_docker_compose.py` /
`scripts/docker_smoke.sh`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_TAG = "money-ledger:pytest"


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=15, check=True)
        return True
    except Exception:
        return False


def _run(*args: str) -> str:
    result = subprocess.run(
        ["docker", "run", "--rm", IMAGE_TAG, *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def built_image():
    if not _docker_ok():
        pytest.skip("docker daemon is not available")
    subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, str(REPO_ROOT)], check=True, timeout=900
    )
    try:
        yield IMAGE_TAG
    finally:
        subprocess.run(
            ["docker", "image", "rm", "-f", IMAGE_TAG], capture_output=True, check=False
        )


def _image_config(tag: str) -> dict:
    out = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config}}", tag],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def test_runs_as_non_root(built_image) -> None:
    uid = _run("id", "-u")
    assert uid != "0"
    assert int(uid) >= 10000  # the fixed app UID from the Dockerfile
    assert _image_config(built_image).get("User") == "app"


def test_healthcheck_and_cmd_are_as_expected(built_image) -> None:
    cfg = _image_config(built_image)
    assert cfg["Cmd"] == [
        "uvicorn",
        "--factory",
        "money_ledger.api.app:create_app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    hc = cfg.get("Healthcheck") or {}
    assert hc.get("Test"), "image must declare a HEALTHCHECK"
    assert any("/api/v1/health" in part for part in hc["Test"])


def test_application_imports_inside_the_image(built_image) -> None:
    _run("python", "-c", "import money_ledger.api; assert money_ledger.api.create_app")


def test_migration_and_server_tooling_present(built_image) -> None:
    assert _run("alembic", "--version")
    assert _run("uvicorn", "--version")


def test_no_dev_artifacts_anywhere_in_the_image(built_image) -> None:
    found = _run(
        "sh",
        "-c",
        "find / -xdev \\( -name .env -o -name conftest.py -o -name pytest.ini "
        "-o -name 'test_*.py' -o -type d -name tests -o -type d -name .pytest_cache "
        "-o -type d -name .git \\) 2>/dev/null || true",
    )
    assert found == "", f"dev artefacts leaked into the image:\n{found}"
    installed = _run("sh", "-c", "pip list 2>/dev/null | tr 'A-Z' 'a-z'")
    assert "pytest" not in installed
    assert "httpx" not in installed
