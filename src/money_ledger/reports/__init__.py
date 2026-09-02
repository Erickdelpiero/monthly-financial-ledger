"""Derived reports (PHASE-2.8, PHASE-2.5 §19-20).

Read-only projections of the ledger. Every number comes from the same
``compute_balance`` / ACTIVE-rows path the rest of the system uses -- a report
never runs its own financial calculation (PHASE-2.8 §3, §15).
"""

from money_ledger.reports.labels import MOVEMENT_LABELS, movement_label
from money_ledger.reports.service import (
    MonthlyReport,
    MonthlyRow,
    WeeklyReport,
    monthly_report,
    weekly_report,
)

__all__ = [
    "MOVEMENT_LABELS",
    "movement_label",
    "WeeklyReport",
    "MonthlyReport",
    "MonthlyRow",
    "weekly_report",
    "monthly_report",
]
