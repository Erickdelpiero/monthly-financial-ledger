"""Text -> (amount, description). Deterministic first; LLM only as fallback."""

from money_ledger.parsing.deterministic import parse_raw_text
from money_ledger.parsing.llm import (
    LLMExtraction,
    LLMExtractor,
    NullLLMExtractor,
    validate_llm_extraction,
)
from money_ledger.parsing.resolver import resolve_amount_and_description
from money_ledger.parsing.result import ParseResult, ParseSource

__all__ = [
    "parse_raw_text",
    "resolve_amount_and_description",
    "ParseResult",
    "ParseSource",
    "LLMExtraction",
    "LLMExtractor",
    "NullLLMExtractor",
    "validate_llm_extraction",
]
