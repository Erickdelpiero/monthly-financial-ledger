"""The shape a successful extraction hands back to the caller."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal


class ParseSource(str, enum.Enum):
    """Which mechanism produced the result. Kept so the pilot can measure how
    often the LLM fallback is actually needed (Phase 1 §7, PHASE-2.4 §6)."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


@dataclass(frozen=True)
class ParseResult:
    """A non-negative, cent-scale ``amount`` and a non-blank ``description``.

    The deterministic parser can return ``amount == 0`` (a user typo); the
    definitive money validation -- strictly positive, in range, not a float --
    happens in ``record_transaction`` (PHASE-2.3 §18). This is only the
    text-extraction result. The LLM path always returns a strictly positive,
    in-range amount (``validate_llm_extraction`` reuses ``normalize_amount``).
    """

    amount: Decimal
    description: str
    source: ParseSource
