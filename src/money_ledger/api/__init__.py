"""Private internal HTTP API (FastAPI). Run locally with:

    PYTHONPATH=src uvicorn --factory money_ledger.api.app:create_app

(the Docker image in Block 5 puts the package on the path). Needs
``DATABASE_URL`` and ``API_INTERNAL_TOKEN`` in the environment.
"""

from money_ledger.api.app import create_app

__all__ = ["create_app"]
