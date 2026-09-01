"""Money value rules (PHASE-2.3 §8, PHASE-2.5 §10, PHASE-2.6 §14).

v1 currency is PEN only. Amounts are exact ``Decimal`` with at most two
decimal places -- real transfers (Yape / Plin / bank) are always integer or
integer.cc. This is the Python pre-insert validation that PHASE-2.3 §18 calls
"amount representable con céntimos"; the NUMERIC(12,2) column would otherwise
round silently (F4 in docs/decisions/block-1-followups.md).
"""

from __future__ import annotations

from decimal import Decimal

from money_ledger.domain.errors import InvalidAmount

CURRENCY = "PEN"

_CENT = Decimal("0.01")
# NUMERIC(12, 2) upper bound.
MAX_AMOUNT = Decimal("9999999999.99")


def validate_amount(value: Decimal) -> Decimal:
    """Return ``value`` unchanged if it is a valid money amount, else raise.

    Valid = a finite ``Decimal``, strictly positive, exactly representable in
    cents, and within the NUMERIC(12,2) range. Floats are rejected outright.
    """
    if not isinstance(value, Decimal):
        raise InvalidAmount("amount must be a Decimal, not %s" % type(value).__name__)
    if not value.is_finite():
        raise InvalidAmount("amount must be a finite decimal")
    if value <= 0:
        raise InvalidAmount("amount must be positive")
    if value != value.quantize(_CENT):
        raise InvalidAmount("amount must be representable in cents (at most 2 decimals)")
    if value > MAX_AMOUNT:
        raise InvalidAmount("amount exceeds the maximum supported value")
    return value


def normalize_amount(value: Decimal) -> Decimal:
    """Validate and return the amount quantized to exactly two decimals."""
    return validate_amount(value).quantize(_CENT)
