"""event_type -> signed effect (PHASE-2.3 §5, PHASE-2.5 §12). Pure, no DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from money_ledger.domain.errors import InvalidEventType
from money_ledger.domain.events import SIGN, parse_event_type, signed_effect
from money_ledger.models.enums import EventType

AMOUNT = Decimal("100.00")


@pytest.mark.parametrize(
    "event_type, expected",
    [
        (EventType.mama_entrega_dinero, Decimal("100.00")),
        (EventType.erick_gasta_para_mama, Decimal("-100.00")),
        (EventType.erick_entrega_dinero, Decimal("-100.00")),
        (EventType.mama_devuelve, Decimal("-100.00")),
        (EventType.erick_devuelve, Decimal("100.00")),
    ],
)
def test_signed_effect_matches_contract(event_type: EventType, expected: Decimal) -> None:
    assert signed_effect(event_type, AMOUNT) == expected


def test_sign_table_covers_every_event_type() -> None:
    assert set(SIGN) == set(EventType)
    assert set(SIGN.values()) <= {-1, 1}


def test_signed_effect_preserves_magnitude_and_is_exact() -> None:
    assert abs(signed_effect(EventType.erick_gasta_para_mama, Decimal("0.01"))) == Decimal("0.01")
    assert isinstance(signed_effect(EventType.mama_devuelve, Decimal("5.55")), Decimal)


def test_signed_effect_accepts_the_string_form() -> None:
    assert signed_effect("mama_entrega_dinero", AMOUNT) == Decimal("100.00")


def test_parse_event_type_round_trips_and_rejects_unknown() -> None:
    assert parse_event_type("erick_devuelve") is EventType.erick_devuelve
    assert parse_event_type(EventType.erick_devuelve) is EventType.erick_devuelve
    with pytest.raises(InvalidEventType):
        parse_event_type("mama_regala_dinero")
