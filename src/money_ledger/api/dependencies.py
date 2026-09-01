"""FastAPI dependencies: DB session, service-token check, LLM handle."""

from __future__ import annotations

import secrets
from typing import Iterator, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from money_ledger.api.errors import Unauthorized
from money_ledger.parsing.llm import LLMExtractor


def get_session(request: Request) -> Iterator[Session]:
    """A request-scoped session. The route's services ``flush`` but never
    ``commit``; the commit happens here once the handler returns cleanly.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    expected: str = request.app.state.api_token
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise Unauthorized("missing or invalid API key")


def get_llm(request: Request) -> Optional[LLMExtractor]:
    """The configured LLM fallback extractor, or ``None`` in v1."""
    return getattr(request.app.state, "llm", None)


ApiKeyGuard = Depends(require_api_key)
