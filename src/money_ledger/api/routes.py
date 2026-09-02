"""The v1 endpoints (PHASE-2.5 §5).

    GET  /health
    POST /transactions
    POST /transactions/{id}/corrections
    GET  /transactions
    GET  /balance
    GET  /reports/weekly
    GET  /reports/monthly
    GET  /reports/monthly/image
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from money_ledger.api.dependencies import ApiKeyGuard, get_llm, get_session
from money_ledger.api.identity import resolve_person
from money_ledger.api.idempotency import correction_replay, transaction_replay
from money_ledger.api.schemas import CorrectionCreate, TransactionCreate
from money_ledger.api.serialization import (
    balance_payload,
    monthly_report_payload,
    transaction_payload,
    weekly_report_payload,
)
from money_ledger.domain.errors import InvalidAmount, InvalidEventDate, ValidationError
from money_ledger.domain.events import parse_event_type
from money_ledger.models.enums import TransactionStatus
from money_ledger.parsing import resolve_amount_and_description
from money_ledger.parsing.result import ParseResult, ParseSource
from money_ledger.reports import monthly_report, weekly_report
from money_ledger.services import (
    apply_correction,
    get_balance,
    list_recent_transactions,
    record_transaction,
)

router = APIRouter()


def _parse_event_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvalidEventDate("event_date must be an ISO date (YYYY-MM-DD)") from None


def _amount_from_string(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise InvalidAmount("amount must be a decimal string") from None


_STATUS_FILTERS = {
    "active": TransactionStatus.ACTIVE,
    "superseded": TransactionStatus.SUPERSEDED,
    "all": None,
}


def _status_filter(value: str) -> Optional[TransactionStatus]:
    try:
        return _STATUS_FILTERS[value]
    except KeyError:
        raise ValidationError(
            "status must be one of: active, superseded, all"
        ) from None


def _with_balance(session: Session, key: str, payload: dict) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={key: payload, "balance": balance_payload(get_balance(session))},
    )


@router.get("/health")
def health(request: Request) -> JSONResponse:
    session_factory = request.app.state.session_factory
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/transactions", dependencies=[ApiKeyGuard])
def create_transaction(
    payload: TransactionCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> JSONResponse:
    person = resolve_person(session, payload.telegram_user_id)
    event_type = parse_event_type(payload.event_type)
    event_date = _parse_event_date(payload.event_date)

    # Idempotency BEFORE the parser / LLM (PHASE-2.9 §6.3).
    replay = transaction_replay(
        session,
        idempotency_key=payload.idempotency_key,
        person_id=person.id,
        event_type=event_type,
        event_date=event_date,
    )
    if replay is not None:
        return _with_balance(session, "transaction", transaction_payload(replay))

    if payload.amount is not None:  # structured path (schema guarantees description)
        parsed = ParseResult(
            amount=_amount_from_string(payload.amount),
            description=payload.description.strip(),
            source=ParseSource.DETERMINISTIC,
        )
    else:
        parsed = resolve_amount_and_description(payload.raw_text, llm=get_llm(request))

    txn = record_transaction(
        session,
        created_by_id=person.id,
        event_type=event_type,
        amount=parsed.amount,
        description=parsed.description,
        event_date=event_date,
        idempotency_key=payload.idempotency_key,
    )
    session.flush()
    return _with_balance(
        session, "transaction", transaction_payload(txn, parse_source=parsed.source)
    )


@router.post("/transactions/{transaction_id}/corrections", dependencies=[ApiKeyGuard])
def create_correction(
    transaction_id: uuid.UUID,
    payload: CorrectionCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> JSONResponse:
    person = resolve_person(session, payload.telegram_user_id)

    event_type = (
        parse_event_type(payload.event_type) if payload.event_type is not None else None
    )
    event_date = (
        _parse_event_date(payload.event_date) if payload.event_date is not None else None
    )

    replay = correction_replay(
        session,
        idempotency_key=payload.idempotency_key,
        target_id=transaction_id,
    )
    if replay is not None:
        return _with_balance(session, "correction", transaction_payload(replay))

    new_amount: Optional[Decimal] = None
    new_description: Optional[str] = None
    if payload.raw_text and payload.raw_text.strip():
        parsed = resolve_amount_and_description(payload.raw_text, llm=get_llm(request))
        new_amount, new_description = parsed.amount, parsed.description
    else:
        if payload.amount is not None:
            new_amount = _amount_from_string(payload.amount)
        # `apply_correction` validates a provided description is non-blank.
        new_description = payload.description

    correction = apply_correction(
        session,
        target_id=transaction_id,
        created_by_id=person.id,
        idempotency_key=payload.idempotency_key,
        event_type=event_type,
        amount=new_amount,
        description=new_description,
        event_date=event_date,
    )
    session.flush()
    return _with_balance(session, "correction", transaction_payload(correction))


@router.get("/transactions", dependencies=[ApiKeyGuard])
def list_transactions(
    telegram_user_id: str = Query(min_length=1),
    status: str = Query(default="active"),
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """A person's recent rows, newest first — for the correction picker
    (PHASE-2.10 §18.1). Read-only projection."""
    person = resolve_person(session, telegram_user_id)
    rows = list_recent_transactions(
        session,
        created_by_id=person.id,
        status=_status_filter(status),
        limit=limit,
    )
    return JSONResponse(
        status_code=200,
        content={"transactions": [transaction_payload(row) for row in rows]},
    )


@router.get("/balance", dependencies=[ApiKeyGuard])
def read_balance(session: Session = Depends(get_session)) -> JSONResponse:
    return JSONResponse(status_code=200, content=balance_payload(get_balance(session)))


@router.get("/reports/weekly", dependencies=[ApiKeyGuard])
def read_weekly_report(session: Session = Depends(get_session)) -> JSONResponse:
    """Text-only weekly report: current bilateral balance + who owes whom
    (PHASE-2.8 §4). Python renders the fixed template; n8n only forwards it."""
    return JSONResponse(
        status_code=200, content=weekly_report_payload(weekly_report(session))
    )


@router.get("/reports/monthly", dependencies=[ApiKeyGuard])
def read_monthly_report(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Executive summary (current balance) + the ACTIVE movements whose
    ``event_date`` falls in the given month (PHASE-2.5 §19, PHASE-2.8 §5)."""
    report = monthly_report(session, year=year, month=month)
    return JSONResponse(status_code=200, content=monthly_report_payload(report))


@router.get("/reports/monthly/image", dependencies=[ApiKeyGuard])
def read_monthly_report_image(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> Response:
    """The monthly report as a PNG (PHASE-2.5 §20, PHASE-2.8 §5-6). matplotlib
    is imported lazily here so the other endpoints don't pay for it."""
    from money_ledger.reports.render import render_monthly_png

    report = monthly_report(session, year=year, month=month)
    return Response(content=render_monthly_png(report), media_type="image/png")
