"""Request models. ``extra="forbid"`` rejects any field n8n must not send --
in particular ``balance`` / ``signed_effect`` / ``signed_amount`` / ``person_id``
(PHASE-2.5 §23, PHASE-2.9 §9.1).

Domain-shaped fields (``event_type``, ``event_date``, ``amount``) are typed as
plain strings here and parsed in the route, so a bad value yields a specific
code (``INVALID_EVENT_TYPE`` ...) rather than a generic ``VALIDATION_ERROR``.

``raw_text`` is the primary input path (PHASE-2.5 §8.1). Structured
``amount`` + ``description`` is a secondary path for tests / controlled
integration; the two are **mutually exclusive** -- a request may not send both.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _is_set(value) -> bool:
    return value is not None and (not isinstance(value, str) or value.strip() != "")


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    event_date: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)

    raw_text: str | None = None
    amount: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _one_input_path(self) -> "TransactionCreate":
        has_raw = _is_set(self.raw_text)
        has_structured = self.amount is not None or self.description is not None
        if has_raw and has_structured:
            raise ValueError("send raw_text OR structured amount/description, not both")
        if not has_raw and not (_is_set(self.amount) and _is_set(self.description)):
            raise ValueError("provide raw_text, or both amount and description")
        return self


class CorrectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)

    # Every field is optional; an omitted field keeps the target's value, but at
    # least one must be present.
    event_type: str | None = None
    event_date: str | None = None
    raw_text: str | None = None
    amount: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "CorrectionCreate":
        has_raw = _is_set(self.raw_text)
        has_structured = self.amount is not None or self.description is not None
        if has_raw and has_structured:
            raise ValueError("send raw_text OR structured amount/description, not both")
        if not any(
            _is_set(v)
            for v in (
                self.event_type,
                self.event_date,
                self.raw_text,
                self.amount,
                self.description,
            )
        ):
            raise ValueError("provide at least one field to correct")
        return self
