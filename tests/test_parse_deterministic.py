"""Deterministic parser (PHASE-2.3 §17, PHASE-2.5 §9.2, PHASE-2.9 §8.1). No DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from money_ledger.domain.errors import ParserFailed, UnsupportedCurrency
from money_ledger.parsing import ParseSource, parse_raw_text


@pytest.mark.parametrize(
    "raw, amount, description",
    [
        ("S/ 35.50 taxi", "35.50", "taxi"),
        ("35.50 taxi", "35.50", "taxi"),
        ("35,50 taxi", "35.50", "taxi"),
        ("S/35.50 taxi", "35.50", "taxi"),
        ("S/. 35.50 taxi", "35.50", "taxi"),
        ("taxi 35.50", "35.50", "taxi"),
        ("50.50 pan y leche", "50.50", "pan y leche"),
        ("pan y leche 50.50", "50.50", "pan y leche"),
        ("S/ 35 taxi", "35.00", "taxi"),
        ("35.5 taxi", "35.50", "taxi"),
        ("  S/   35.50    taxi  ", "35.50", "taxi"),
        ("S/35.50, pan y leche", "35.50", "pan y leche"),
        ("0 taxi", "0.00", "taxi"),  # parser extracts; record_transaction rejects
        ("pre-pago 20.00", "20.00", "pre-pago"),   # hyphen inside a word is fine
        ("wifi-mensual 30", "30.00", "wifi-mensual"),
        ("35.50 - taxi", "35.50", "taxi"),         # dash as separator after amount
        ("1000000000 pan", "1000000000.00", "pan"),        # 10 integer digits
        ("9999999999.99 pan", "9999999999.99", "pan"),     # NUMERIC(12,2) max
    ],
)
def test_parses_expected_inputs(raw: str, amount: str, description: str) -> None:
    result = parse_raw_text(raw)
    assert result.amount == Decimal(amount)
    assert result.amount.as_tuple().exponent == -2
    assert result.description == description
    assert result.source is ParseSource.DETERMINISTIC


@pytest.mark.parametrize(
    "raw",
    [
        "taxi",                 # no amount
        "gasté algo en taxi",   # no amount
        "35.50",                # no description
        "",                     # empty
        "    ",                 # blank
        "35.50 40.00 taxi",     # more than one number
        "2 panes 5.00",         # more than one number
        "35.999 taxi",          # not a valid cent amount -> no clean token
        "1.500,50 taxi",        # digit grouping -> leftover digits in description
        "10000000000 pan",      # 11 integer digits -> out of NUMERIC(12,2) range
    ],
)
def test_rejects_unparseable_inputs(raw: str) -> None:
    with pytest.raises(ParserFailed):
        parse_raw_text(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "-35.50 taxi",
        "S/ -35.50 taxi",
        "S/-0.01 ajuste",
        "+35.50 taxi",
        "S/ +100 abono",
        "- 35.50 taxi",
        "taxi -35.50",
        "−35.50 taxi",  # U+2212 minus
    ],
)
def test_rejects_signed_amounts(raw: str) -> None:
    """A sign is never reinterpreted -- direction comes from the event-type button."""
    with pytest.raises(ParserFailed):
        parse_raw_text(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "$50 taxi",
        "US$ 50 taxi",
        "USD 50 taxi",
        "50 dólares taxi",
        "50 dolares en taxi",
        "50€ pan",
        "EUR 50 pan",
        "50 euros pan",
    ],
)
def test_foreign_currency_is_terminal(raw: str) -> None:
    with pytest.raises(UnsupportedCurrency):
        parse_raw_text(raw)


def test_non_string_input_is_rejected() -> None:
    with pytest.raises(ParserFailed):
        parse_raw_text(None)  # type: ignore[arg-type]
