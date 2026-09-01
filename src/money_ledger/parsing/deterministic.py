"""Deterministic parser -- the primary path (PHASE-2.3 §16-17, PHASE-2.5 §9.2).

Grammar for v1 (a personal two-user bot; inputs look like ``S/ 35.50 taxi``):

* currency: PEN only. ``S/``, ``S/.``, ``soles``, ``PEN`` are stripped; any
  foreign-currency marker (``$``, ``USD``, ``€`` ...) raises
  :class:`UnsupportedCurrency` -- a **terminal** error (the LLM fallback must
  never reinterpret it).
* amount: exactly ONE number token of 1-10 integer digits (the NUMERIC(12,2)
  integer range) with an optional ``.``/``,`` decimal part of 1-2 digits.
  Digit-grouping separators are not supported.
* a sign directly before the amount (``-35.50``, ``+35.50``, ``- 35.50``) is
  **rejected**, not reinterpreted -- direction is set by the event-type button,
  never by a sign in the text.
* zero, more than one number, no leftover description, or a description that
  still contains digits → :class:`ParserFailed` (recoverable; the caller may
  try the LLM fallback). ``0`` *is* extracted so ``record_transaction`` can
  return the precise ``INVALID_AMOUNT`` -- the parser stays about text only.

There is deliberately no ``confidence_score`` (PHASE-2.9 §8.3).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from money_ledger.domain.errors import ParserFailed, UnsupportedCurrency
from money_ledger.parsing.result import ParseResult, ParseSource

_CENT = Decimal("0.01")

# One clean PEN amount token, not glued to other digits/separators.
# 1-10 integer digits == the NUMERIC(12,2) integer range (see B3 notes).
_AMOUNT_RE = re.compile(r"(?<![\d.,])\d{1,10}(?:[.,]\d{1,2})?(?![\d.,]\d)")

# Peruvian-sol markers, stripped before parsing.
_PEN_RE = re.compile(r"(?i)\bs/\.?|\bsoles?\b|\bpen\b")

# Foreign-currency markers -> terminal (v1 is PEN only).
_FOREIGN_RE = re.compile(
    r"(?i)(?:us)?\$|\busd\b|€|\beur\b|£|\bgbp\b|\bd[oó]lares?\b|\beuros?\b"
)

_SIGN_CHARS = ("-", "+", "−")  # hyphen-minus, plus, U+2212 minus
_WS_RE = re.compile(r"\s+")
_EDGE_PUNCT = " \t\n\r.,;:-—·"


def parse_raw_text(raw_text: str) -> ParseResult:
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ParserFailed("empty input")

    text = _WS_RE.sub(" ", raw_text).strip()

    if _FOREIGN_RE.search(text):
        raise UnsupportedCurrency("unsupported currency (v1 handles PEN only)")

    without_currency = _PEN_RE.sub(" ", text)
    matches = list(_AMOUNT_RE.finditer(without_currency))
    if not matches:
        raise ParserFailed("no amount found")
    if len(matches) > 1:
        raise ParserFailed("more than one number; cannot choose an amount")

    match = matches[0]
    if without_currency[: match.start()].rstrip().endswith(_SIGN_CHARS):
        raise ParserFailed("signed amounts are not accepted; enter a positive amount")

    raw_amount = match.group(0)
    description = f"{without_currency[: match.start()]} {without_currency[match.end():]}"
    description = _WS_RE.sub(" ", description).strip(_EDGE_PUNCT).strip()

    if not description:
        raise ParserFailed("amount found but no description")
    if any(ch.isdigit() for ch in description):
        raise ParserFailed("description still contains digits; input is ambiguous")

    try:
        amount = Decimal(raw_amount.replace(",", ".")).quantize(_CENT)
    except InvalidOperation:  # pragma: no cover - the regex already constrains this
        raise ParserFailed(f"could not read amount {raw_amount!r}") from None

    return ParseResult(
        amount=amount, description=description, source=ParseSource.DETERMINISTIC
    )
