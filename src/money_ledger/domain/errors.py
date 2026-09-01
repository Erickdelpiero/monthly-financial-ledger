"""Domain error hierarchy.

Each error carries a stable ``code`` string. The API layer (Block 4) maps these
codes to HTTP responses; nothing outside this module should hard-code the code
strings' meanings. Codes align with PHASE-2.5 §17 where one exists there.
"""

from __future__ import annotations


class LedgerError(Exception):
    """Base for every expected domain error."""

    code = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code


class ValidationError(LedgerError):
    code = "VALIDATION_ERROR"


class InvalidAmount(ValidationError):
    code = "INVALID_AMOUNT"


class InvalidEventType(ValidationError):
    code = "INVALID_EVENT_TYPE"


class InvalidEventDate(ValidationError):
    code = "INVALID_EVENT_DATE"


class InvalidDescription(ValidationError):
    code = "VALIDATION_ERROR"


class InvalidIdempotencyKey(ValidationError):
    code = "VALIDATION_ERROR"


class UnknownPerson(LedgerError):
    # Block 4 resolves telegram_user_id -> person and reports UNKNOWN_TELEGRAM_USER;
    # at the domain boundary we only know a person_id was not found.
    code = "UNKNOWN_PERSON"


class InactivePerson(LedgerError):
    code = "INACTIVE_PERSON"


class TransactionNotFound(LedgerError):
    code = "TRANSACTION_NOT_FOUND"


class TransactionNotActive(LedgerError):
    code = "TRANSACTION_NOT_ACTIVE"


class CorrectionNotAllowed(LedgerError):
    """The correcting actor is not the person who registered the target row.

    v1 policy: each person corrects only their own entries
    (PHASE-2.10 §18.1 / §29.9).
    """

    code = "CORRECTION_NOT_ALLOWED"


class DuplicateIdempotencyKey(LedgerError):
    code = "DUPLICATE_IDEMPOTENCY_KEY"


class ParserFailed(LedgerError):
    """The deterministic parser could not extract amount + description.

    Recoverable: the caller may try the LLM fallback.
    """

    code = "PARSER_FAILED"


class UnsupportedCurrency(ParserFailed):
    """A non-PEN currency marker was found in the input.

    Terminal: v1 is PEN-only, and the LLM fallback must never reinterpret a
    foreign-currency amount as PEN (PHASE-2.3 §8, PHASE-2.5 §10).
    """


class LLMFallbackError(LedgerError):
    """The LLM fallback is unavailable, errored, or returned an invalid result."""

    code = "LLM_FALLBACK_ERROR"
