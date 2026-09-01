"""LLM fallback contract (PHASE-2.3 §17, PHASE-2.5 §9.3, PHASE-2.9 §8.2). No DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from money_ledger.domain.errors import LLMFallbackError
from money_ledger.parsing import (
    LLMExtraction,
    NullLLMExtractor,
    ParseSource,
    validate_llm_extraction,
)


def test_null_extractor_always_fails() -> None:
    with pytest.raises(LLMFallbackError):
        NullLLMExtractor().extract("S/ 35.50 taxi")


def test_valid_mapping_result() -> None:
    result = validate_llm_extraction({"amount": "35.50", "description": "taxi"})
    assert result.amount == Decimal("35.50")
    assert result.description == "taxi"
    assert result.source is ParseSource.LLM


def test_valid_dataclass_result_and_normalization() -> None:
    result = validate_llm_extraction(LLMExtraction(amount="35,5", description="  taxi "))
    assert result.amount == Decimal("35.50")
    assert result.description == "taxi"


@pytest.mark.parametrize(
    "forbidden",
    [
        "event_type",
        "signed_effect",
        "signed_amount",
        "balance",
        "direction",
        "person_id",
        "telegram_user_id",
        "created_by_id",
        "status",
        "payer",
    ],
)
def test_forbidden_fields_are_rejected(forbidden: str) -> None:
    payload = {"amount": "35.50", "description": "taxi", forbidden: "whatever"}
    with pytest.raises(LLMFallbackError, match="forbidden"):
        validate_llm_extraction(payload)


def test_unexpected_extra_field_is_rejected() -> None:
    with pytest.raises(LLMFallbackError, match="unexpected"):
        validate_llm_extraction(
            {"amount": "35.50", "description": "taxi", "confidence": 0.9}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "taxi"},                          # missing amount
        {"amount": "abc", "description": "taxi"},         # not a number
        {"amount": "-5.00", "description": "taxi"},       # not positive
        {"amount": "0", "description": "taxi"},           # not positive
        {"amount": "35.999", "description": "taxi"},      # sub-cent
        {"amount": "10000000000.00", "description": "x"}, # exceeds NUMERIC(12,2)
        {"amount": "nan", "description": "taxi"},         # non-finite
        {"amount": "inf", "description": "taxi"},         # non-finite
        {"amount": 35.5, "description": "taxi"},          # float, not a string
        {"amount": Decimal("35.50"), "description": "x"}, # Decimal, not a string
        {"amount": "35.50", "description": "   "},        # blank description
        {"amount": "35.50"},                              # missing description
        {"amount": "35.50", "description": 7},            # description not a string
    ],
)
def test_malformed_results_are_rejected(payload: dict) -> None:
    with pytest.raises(LLMFallbackError):
        validate_llm_extraction(payload)


def test_non_mapping_payload_is_rejected() -> None:
    with pytest.raises(LLMFallbackError):
        validate_llm_extraction("35.50 taxi")
