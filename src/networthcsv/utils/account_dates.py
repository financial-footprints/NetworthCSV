"""Account config date helpers (DD-MM-YYYY), not statement OCR dates."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount

_ACCOUNT_DATE_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


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
    match = _ACCOUNT_DATE_PATTERN.fullmatch(stripped)
    if match is None:
        raise ValueError(f"{field_name} must be in DD-MM-YYYY format")
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    if month < 1 or month > 12:
        raise ValueError(f"{field_name} month must be between 01 and 12")
    if day < 1 or day > 31:
        raise ValueError(f"{field_name} day must be between 01 and 31")
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid calendar date") from exc


def parse_opening_date(value: object) -> date | None:
    return parse_account_date(value, "opening_date")


def parse_closing_date(value: object) -> date | None:
    return parse_account_date(value, "closing_date")


def format_account_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d-%m-%Y")


def require_account_date_str(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def exclusive_search_end_date(end_date: date) -> date:
    """Return the day after ``end_date`` for an exclusive IMAP/Gmail ``BEFORE`` bound."""
    return end_date + timedelta(days=1)


def incremental_fetch_start(last_fetch_date: date | None) -> date | None:
    if last_fetch_date is None:
        return None
    return last_fetch_date - timedelta(days=1)


def resolve_account_search_dates(
    account: ResolvedAccount,
    global_start_date: date | None,
    *,
    last_fetch_date: date | None = None,
) -> tuple[date | None, date | None]:
    start_candidates: list[date] = []
    if global_start_date is not None:
        start_candidates.append(global_start_date)
    start_candidates.append(account.opening_date)
    incremental_start = incremental_fetch_start(last_fetch_date)
    if incremental_start is not None:
        start_candidates.append(incremental_start)
    effective_start = max(start_candidates) if start_candidates else None
    effective_end = (
        exclusive_search_end_date(account.closing_date)
        if account.closing_date is not None
        else None
    )
    return effective_start, effective_end
