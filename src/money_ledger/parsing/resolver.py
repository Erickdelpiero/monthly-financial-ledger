"""Deterministic-first resolution with an optional LLM fallback (PHASE-2.5 §9)."""

from __future__ import annotations

from typing import Optional

from money_ledger.domain.errors import (
    LLMFallbackError,
    ParserFailed,
    UnsupportedCurrency,
)
from money_ledger.parsing.deterministic import parse_raw_text
from money_ledger.parsing.llm import LLMExtractor, validate_llm_extraction
from money_ledger.parsing.result import ParseResult


def resolve_amount_and_description(
    raw_text: str, *, llm: Optional[LLMExtractor] = None
) -> ParseResult:
    """Return the amount + description for ``raw_text``.

    The deterministic parser runs first and always wins when it succeeds -- the
    LLM is never consulted on the happy path. A :class:`UnsupportedCurrency`
    failure is terminal and never falls back. For any other
    :class:`ParserFailed`, if no LLM is given it propagates; otherwise the LLM
    result is passed through :func:`validate_llm_extraction` and any extractor
    error or invalid result surfaces as :class:`LLMFallbackError`.
    """
    try:
        return parse_raw_text(raw_text)
    except UnsupportedCurrency:
        raise  # terminal: a non-PEN amount is never reinterpreted by the LLM
    except ParserFailed:
        if llm is None:
            raise

    try:
        extraction = llm.extract(raw_text)
    except LLMFallbackError:
        raise
    except Exception as exc:  # noqa: BLE001 - any extractor failure is a fallback error
        raise LLMFallbackError(
            f"LLM extractor raised {type(exc).__name__}: {exc}"
        ) from exc

    return validate_llm_extraction(extraction)
