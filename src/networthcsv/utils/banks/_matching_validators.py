"""Private validators for mail/statement matching fields."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast

from pydantic import BeforeValidator

from networthcsv.utils._validators import optional_normalizer as _optional


def normalize_account_type(value: object) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if not raw:
        return "credit_card"
    if raw not in ("bank_account", "credit_card"):
        raise ValueError("type must be bank_account or credit_card")
    return raw


def _optional_account_type(value: object) -> str | None:
    if value is None or value == "":
        return None
    return normalize_account_type(value)


def _normalize_from_entry(entry: str) -> str:
    if any(ch.isspace() for ch in entry):
        raise ValueError("from entries must not contain whitespace")
    if "@" in entry:
        local, sep, domain = entry.partition("@")
        if not local or not sep or not domain or "@" in domain:
            raise ValueError(f"invalid from email address: {entry!r}")
    return entry


def normalize_string_list(
    value: object,
    *,
    field_name: str,
    required: bool = False,
    allow_empty: bool = True,
    list_only: bool = False,
    case_insensitive_dedupe: bool = False,
    lowercase_items: bool = False,
    item_validator: Callable[[str], str] | None = None,
) -> list[str]:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} must contain at least one non-empty value")
        return []

    if list_only:
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field_name} must be a non-empty array")
        items = cast(list[object], value)
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        shape = "a non-empty array" if required else "a string or an array"
        raise ValueError(f"{field_name} must be {shape}")

    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if lowercase_items:
            text = text.lower()
        if item_validator is not None:
            text = item_validator(text)
        dedupe_key = text.lower() if case_insensitive_dedupe else text
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            unique.append(text)

    if required and not unique:
        raise ValueError(f"{field_name} must contain at least one non-empty value")
    if not allow_empty and not unique and value not in (None, ""):
        raise ValueError(f"{field_name} must contain at least one non-empty value")
    return unique


def normalize_subjects(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="subjects",
        required=True,
        allow_empty=False,
        case_insensitive_dedupe=True,
    )


def normalize_body_contains(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="body_contains",
        case_insensitive_dedupe=True,
    )


def normalize_from(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="from",
        lowercase_items=True,
        item_validator=_normalize_from_entry,
    )


def normalize_text_contains(value: object) -> list[str]:
    return normalize_string_list(value, field_name="text_contains")


def normalize_text_not_contains(value: object) -> list[str]:
    return normalize_string_list(value, field_name="text_not_contains")


Subjects = Annotated[list[str], BeforeValidator(normalize_subjects)]
OptionalSubjects = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_subjects))
]
BodyContains = Annotated[list[str], BeforeValidator(normalize_body_contains)]
OptionalBodyContains = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_body_contains))
]
FromAddresses = Annotated[list[str], BeforeValidator(normalize_from)]
OptionalFromAddresses = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_from))
]
AccountTypeName = Annotated[str, BeforeValidator(normalize_account_type)]
OptionalAccountTypeName = Annotated[str | None, BeforeValidator(_optional_account_type)]
TextContains = Annotated[list[str], BeforeValidator(normalize_text_contains)]
OptionalTextContains = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_text_contains))
]
TextNotContains = Annotated[list[str], BeforeValidator(normalize_text_not_contains)]
OptionalTextNotContains = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_text_not_contains))
]
