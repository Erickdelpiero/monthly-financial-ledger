"""HTTP error surface: stable codes + a fixed ``{"error": {...}}`` envelope.

n8n decides UX from ``error.code``, never from the message text (PHASE-2.5 §17).
Codes align with PHASE-2.5 §17 / PHASE-2.10 §21.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from money_ledger.domain.errors import LedgerError

logger = logging.getLogger("money_ledger.api")


class Unauthorized(LedgerError):
    code = "UNAUTHORIZED"


class UnknownTelegramUser(LedgerError):
    code = "UNKNOWN_TELEGRAM_USER"


_STATUS_BY_CODE = {
    "UNAUTHORIZED": 401,
    "UNKNOWN_TELEGRAM_USER": 403,
    "UNKNOWN_PERSON": 403,
    "INACTIVE_PERSON": 403,
    "TRANSACTION_NOT_FOUND": 404,
    "TRANSACTION_NOT_ACTIVE": 409,
    "CORRECTION_NOT_ALLOWED": 403,
    "DUPLICATE_IDEMPOTENCY_KEY": 409,
    "INVALID_AMOUNT": 422,
    "INVALID_EVENT_TYPE": 422,
    "INVALID_EVENT_DATE": 422,
    "PARSER_FAILED": 422,
    "LLM_FALLBACK_ERROR": 422,
    "VALIDATION_ERROR": 422,
    "INTERNAL_ERROR": 500,
}


def _envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _summarize_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else err.get("msg", "invalid"))
    return "; ".join(parts) or "request validation failed"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LedgerError)
    async def _ledger_error(request: Request, exc: LedgerError) -> JSONResponse:
        status = _STATUS_BY_CODE.get(exc.code, 422)
        return JSONResponse(status_code=status, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", _summarize_validation(exc)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=_envelope("INTERNAL_ERROR", "internal error")
        )
