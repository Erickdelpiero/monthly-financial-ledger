"""LLM fallback -- the CONTRACT only. No real provider is wired in v1.

The LLM may return exactly ``{amount, description}`` and nothing else
(PHASE-2.3 §17, PHASE-2.5 §9.3, PHASE-2.9 §8.2). It must never decide
``event_type``, identity, a sign, or the balance. ``validate_llm_extraction``
enforces that allow-list and re-checks the amount before the value is allowed
anywhere near the domain.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

from money_ledger.domain.errors import InvalidAmount, LLMFallbackError
from money_ledger.domain.money import normalize_amount
from money_ledger.parsing.result import ParseResult, ParseSource

_ALLOWED_KEYS = frozenset({"amount", "description"})
_FORBIDDEN_KEYS = frozenset(
    {
        "event_type",
        "signed_effect",
        "signed_amount",
        "balance",
        "direction",
        "person_id",
        "telegram_user_id",
        "created_by",
        "created_by_id",
        "status",
        "payer",
        "receiver",
    }
)


@dataclass(frozen=True)
class LLMExtraction:
    amount: str
    description: str


@runtime_checkable
class LLMExtractor(Protocol):
    def extract(self, raw_text: str) -> "LLMExtraction | Mapping[str, object]": ...


class NullLLMExtractor:
    """v1 default: no LLM is configured, so any fallback attempt fails cleanly."""

    def extract(self, raw_text: str) -> LLMExtraction:  # noqa: ARG002
        raise LLMFallbackError("no LLM extractor is configured")


def validate_llm_extraction(payload: object) -> ParseResult:
    """Turn a raw LLM result into a trusted :class:`ParseResult` or raise."""
    if isinstance(payload, LLMExtraction):
        data: dict = {"amount": payload.amount, "description": payload.description}
    elif isinstance(payload, Mapping):
        data = dict(payload)
    else:
        raise LLMFallbackError(
            f"LLM result must be a mapping or LLMExtraction, got {type(payload).__name__}"
        )

    forbidden = sorted(_FORBIDDEN_KEYS.intersection(data))
    if forbidden:
        raise LLMFallbackError(f"LLM returned forbidden field(s): {', '.join(forbidden)}")
    unexpected = sorted(set(data) - _ALLOWED_KEYS)
    if unexpected:
        raise LLMFallbackError(
            f"LLM returned unexpected field(s): {', '.join(unexpected)}"
        )

    raw_amount = data.get("amount")
    # PHASE-2.5 §9.3 / §10: the provider contract is decimal *strings* only.
    if not isinstance(raw_amount, str):
        raise LLMFallbackError("LLM 'amount' must be a decimal string")
    try:
        parsed = Decimal(raw_amount.strip().replace(",", "."))
    except InvalidOperation:
        raise LLMFallbackError(f"LLM 'amount' is not a number: {raw_amount!r}") from None
    try:
        # Reuse the central money rule: finite, positive, cent-scale, in range.
        amount = normalize_amount(parsed)
    except InvalidAmount as exc:
        raise LLMFallbackError(f"LLM 'amount' is invalid: {exc.message}") from exc

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise LLMFallbackError("LLM 'description' must be a non-empty string")

    return ParseResult(
        amount=amount, description=description.strip(), source=ParseSource.LLM
    )
