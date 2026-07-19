"""Private field validators for settings config models."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from pydantic import BeforeValidator

from networthcsv.utils._validators import optional_normalizer as _optional
from networthcsv.utils.banks._matching_validators import normalize_string_list


def normalize_bank(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("bank is required")
    if "/" in raw or "\\" in raw:
        raise ValueError("bank must not contain path separators")
    return raw


def normalize_variant(value: object) -> str | None:
    if value is None or value == "":
        return None
    variant = str(value).strip().lower()
    if not variant:
        return None
    if "/" in variant or "\\" in variant:
        raise ValueError("variant must not contain path separators")
    return variant


def normalize_marker(value: object) -> str | None:
    if value is None or value == "":
        return None
    marker = str(value).strip()
    return marker or None


def normalize_account_number(value: object) -> str:
    account_number = str(value or "").strip()
    if not account_number:
        raise ValueError("account_number is required")
    return account_number


def normalize_passwords(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="passwords",
        required=True,
        allow_empty=False,
        list_only=True,
    )


def normalize_alert_recipients(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="to",
        required=True,
        allow_empty=False,
        case_insensitive_dedupe=True,
    )


def _require_non_empty(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _require_field(field_name: str) -> Callable[[object], str]:
    def validate(value: object) -> str:
        return _require_non_empty(value, field_name=field_name)

    return validate


Marker = Annotated[str | None, BeforeValidator(normalize_marker)]
BankName = Annotated[str, BeforeValidator(normalize_bank)]
VariantName = Annotated[str | None, BeforeValidator(normalize_variant)]
AccountNumber = Annotated[str, BeforeValidator(normalize_account_number)]
OptionalIdentifier = Annotated[
    str | None, BeforeValidator(_optional(normalize_account_number))
]
Passwords = Annotated[list[str], BeforeValidator(normalize_passwords)]
