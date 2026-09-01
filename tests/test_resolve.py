"""resolve_amount_and_description: deterministic-first, LLM fallback (PHASE-2.5 §9). No DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from money_ledger.domain.errors import (
    LLMFallbackError,
    ParserFailed,
    UnsupportedCurrency,
)
from money_ledger.parsing import NullLLMExtractor, ParseSource, resolve_amount_and_description


class RecordingLLM:
    def __init__(self, *, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def extract(self, raw_text: str):
        self.calls.append(raw_text)
        if self.error is not None:
            raise self.error
        return self.result


def test_deterministic_happy_path_never_calls_the_llm() -> None:
    llm = RecordingLLM(result={"amount": "999.99", "description": "hax"})
    result = resolve_amount_and_description("S/ 10.00 pan", llm=llm)
    assert result.amount == Decimal("10.00")
    assert result.description == "pan"
    assert result.source is ParseSource.DETERMINISTIC
    assert llm.calls == []


def test_parser_failure_without_llm_propagates() -> None:
    with pytest.raises(ParserFailed):
        resolve_amount_and_description("me gasté un montón en el taxi")


@pytest.mark.parametrize(
    "raw", ["USD 50 taxi", "$50 taxi", "50 EUR pan", "50 euros pan", "50 dólares taxi"]
)
def test_foreign_currency_is_terminal_and_never_calls_the_llm(raw: str) -> None:
    llm = RecordingLLM(result={"amount": "50.00", "description": "taxi"})
    with pytest.raises(UnsupportedCurrency):
        resolve_amount_and_description(raw, llm=llm)
    assert llm.calls == []


def test_signed_amount_is_a_recoverable_parse_failure() -> None:
    # The deterministic parser rejects the sign; the LLM fallback still runs.
    with pytest.raises(ParserFailed):
        resolve_amount_and_description("-35.50 taxi")

    llm = RecordingLLM(result={"amount": "35.50", "description": "taxi"})
    result = resolve_amount_and_description("-35.50 taxi", llm=llm)
    assert result.amount == Decimal("35.50")
    assert llm.calls == ["-35.50 taxi"]


def test_falls_back_to_llm_on_ambiguous_input() -> None:
    llm = RecordingLLM(result={"amount": "85.00", "description": "pan"})
    result = resolve_amount_and_description("gasté 35 y 50 en pan", llm=llm)
    assert result.amount == Decimal("85.00")
    assert result.description == "pan"
    assert result.source is ParseSource.LLM
    assert llm.calls == ["gasté 35 y 50 en pan"]


def test_null_llm_fallback_raises_fallback_error() -> None:
    with pytest.raises(LLMFallbackError):
        resolve_amount_and_description("bla bla bla", llm=NullLLMExtractor())


def test_llm_extractor_exception_becomes_fallback_error() -> None:
    llm = RecordingLLM(error=RuntimeError("boom"))
    with pytest.raises(LLMFallbackError):
        resolve_amount_and_description("bla bla bla", llm=llm)


def test_llm_result_with_forbidden_field_is_rejected() -> None:
    llm = RecordingLLM(
        result={"amount": "5.00", "description": "x", "event_type": "mama_devuelve"}
    )
    with pytest.raises(LLMFallbackError):
        resolve_amount_and_description("bla bla bla", llm=llm)


def test_llm_result_with_bad_amount_is_rejected() -> None:
    llm = RecordingLLM(result={"amount": "nope", "description": "x"})
    with pytest.raises(LLMFallbackError):
        resolve_amount_and_description("bla bla bla", llm=llm)
