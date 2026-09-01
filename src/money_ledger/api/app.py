"""FastAPI application factory (PHASE-2.5, PHASE-2.7 §14).

Private, internal service: n8n reaches it over the cluster network with an
``X-API-Key`` header. It is never exposed to the internet (PHASE-2.5 §4/§23).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from money_ledger.api.errors import register_error_handlers
from money_ledger.api.routes import router
from money_ledger.config import get_api_token, get_database_url
from money_ledger.db.session import build_engine, build_sessionmaker
from money_ledger.parsing.llm import LLMExtractor


def create_app(
    *,
    database_url: Optional[str] = None,
    api_token: Optional[str] = None,
    llm: Optional[LLMExtractor] = None,
) -> FastAPI:
    engine = build_engine(database_url or get_database_url())
    session_factory = build_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="money-ledger internal API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.api_token = api_token if api_token is not None else get_api_token()
    app.state.llm = llm  # v1: None (no LLM provider wired)

    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return app
