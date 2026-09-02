"""JSON shapes for responses. Amounts are decimal strings (PHASE-2.5 §10/§13)."""

from __future__ import annotations

from typing import Optional

from money_ledger.domain.balance import Balance
from money_ledger.models.transaction import Transaction
from money_ledger.parsing.result import ParseSource
from money_ledger.reports.service import MonthlyReport, WeeklyReport


def balance_payload(balance: Balance) -> dict:
    return {
        "balance": str(balance.amount),
        "currency": balance.currency,
        "direction": balance.direction.value,
    }


def transaction_payload(
    txn: Transaction, *, parse_source: Optional[ParseSource] = None
) -> dict:
    payload = {
        "id": str(txn.id),
        "event_type": txn.event_type.value,
        "amount": str(txn.amount),
        "description": txn.description,
        "event_date": txn.event_date.isoformat(),
        "recorded_at": txn.recorded_at.isoformat(),
        "status": txn.status.value,
        "created_by": str(txn.created_by_id),
        "superseded_by": str(txn.superseded_by_id) if txn.superseded_by_id else None,
    }
    if parse_source is not None:
        payload["parse_source"] = parse_source.value
    return payload


def weekly_report_payload(report: WeeklyReport) -> dict:
    return {"text": report.text, "balance": balance_payload(report.balance)}


def monthly_report_payload(report: MonthlyReport) -> dict:
    return {
        "year": report.year,
        "month": report.month,
        "period": report.period_label,
        "balance": balance_payload(report.balance),
        "movements": [
            {
                "event_date": row.event_date.isoformat(),
                "recorded_at": row.recorded_at.isoformat(),
                "person": row.person_name,
                "event_type": row.event_type.value,
                "movement": row.movement_label,
                "amount": str(row.amount),
                "description": row.description,
            }
            for row in report.rows
        ],
    }
