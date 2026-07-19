"""Account config date helpers (DD-MM-YYYY), not statement OCR dates."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount

_ACCOUNT_DATE_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
_ISO_ACCOUNT_DATE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MIN_ACCOUNT_DATE = date(1970, 1, 1)
MIN_ACCOUNT_DATE_STR = "01-01-1970"


def max_account_date(*, today: date | None = None) -> date:
    current = today or date.today()
    return date(current.year, 12, 31)


def max_account_date_str(*, today: date | None = None) -> str:
    max_date = max_account_date(today=today)
    return _format_account_date_parts(max_date.day, max_date.month, max_date.year)


def _format_account_date_parts(day: int, month: int, year: int) -> str:
    return f"{day:02d}-{month:02d}-{year:04d}"


def _validate_account_date_range(
    parsed: date,
    field_name: str,
    *,
    today: date | None = None,
) -> None:
    if parsed < MIN_ACCOUNT_DATE:
        raise ValueError(f"{field_name} must be on or after {MIN_ACCOUNT_DATE_STR}")
    max_date = max_account_date(today=today)
    if parsed > max_date:
        raise ValueError(
            f"{field_name} must not be after {max_account_date_str(today=today)}"
        )


def _parse_account_date_parts(
    value: str,
    field_name: str,
) -> tuple[int, int, int]:
    match = _ACCOUNT_DATE_PATTERN.fullmatch(value)
    if match is not None:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    iso_match = _ISO_ACCOUNT_DATE_PATTERN.fullmatch(value)
    if iso_match is not None:
        return (
            int(iso_match.group(3)),
            int(iso_match.group(2)),
            int(iso_match.group(1)),
        )

    raise ValueError(f"{field_name} must be in DD-MM-YYYY format")


def parse_account_date(value: object, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a DD-MM-YYYY string or null")
    stripped = value.strip()
    if not stripped:
        return None
    day, month, year = _parse_account_date_parts(stripped, field_name)
    if month < 1 or month > 12:
        raise ValueError(f"{field_name} month must be between 01 and 12")
    if day < 1 or day > 31:
        raise ValueError(f"{field_name} day must be between 01 and 31")
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid calendar date") from exc
    _validate_account_date_range(parsed, field_name)
    return parsed


def parse_opening_date(value: object) -> date | None:
    return parse_account_date(value, "opening_date")


def parse_closing_date(value: object) -> date | None:
    return parse_account_date(value, "closing_date")


def format_account_date(value: date | None) -> str | None:
    if value is None:
        return None
    return _format_account_date_parts(value.day, value.month, value.year)


def require_account_date_str(value: date) -> str:
    return _format_account_date_parts(value.day, value.month, value.year)


def exclusive_search_end_date(end_date: date) -> date:
    """Return the day after ``end_date`` for an exclusive IMAP/Gmail ``BEFORE`` bound."""
    return end_date + timedelta(days=1)


def incremental_fetch_start(last_fetch_date: date | None) -> date | None:
    if last_fetch_date is None:
        return None
    return last_fetch_date - timedelta(days=1)


def resolve_account_search_dates(
    account: ResolvedAccount,
    *,
    last_fetch_date: date | None = None,
) -> tuple[date | None, date | None]:
    start_candidates: list[date] = [account.opening_date]
    incremental_start = incremental_fetch_start(last_fetch_date)
    if incremental_start is not None:
        start_candidates.append(incremental_start)
    effective_start = max(start_candidates)
    effective_end = (
        exclusive_search_end_date(account.closing_date)
        if account.closing_date is not None
        else None
    )
    return effective_start, effective_end
