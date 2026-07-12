"""Statement period identifiers for monthly and yearly statements.

Monthly statements use ``YYYY-MM`` (e.g. ``2024-04``).
Yearly statements use ``yearly-YYYY-MM_YYYY-MM`` (e.g. ``yearly-2024-04_2025-03``).
Also includes fiscal/calendar year keys for metadata grouping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

YearDisplay = Literal["fiscal_year", "calendar_year"]

MONTH_PERIOD_PATTERN = re.compile(r"^(\d{4}-\d{2})$")
FILENAME_MONTH_PATTERN = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")
_STAGING_EMAIL_DATE_PATTERN = re.compile(
    r"__(\d{4}-\d{2}-\d{2})(?:\s+\(\d+\))?\.pdf$",
    re.IGNORECASE,
)
YEARLY_PERIOD_PATTERN = re.compile(
    r"^yearly-(\d{4}-\d{2})_(\d{4}-\d{2})$",
)
_FISCAL_YEAR_KEY_PATTERN = re.compile(r"^FY(\d{2})-(\d{4})$")
_CALENDAR_YEAR_KEY_PATTERN = re.compile(r"^(\d{4})$")

_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_month_period(period: str) -> str | None:
    """Return ``YYYY-MM`` if *period* is a valid monthly period identifier."""
    match = MONTH_PERIOD_PATTERN.fullmatch(period)
    if match is None:
        return None
    return match.group(1)


def month_period_from_filename(filename: str) -> str:
    """Extract ``YYYY-MM`` from a filename, or ``unknown-month`` if not found."""
    match = FILENAME_MONTH_PATTERN.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"


def email_date_from_staging_filename(filename: str) -> date | None:
    """Return the email received date encoded in a staging PDF name, if present."""
    name = Path(filename).name
    match = _STAGING_EMAIL_DATE_PATTERN.search(name)
    if match is None:
        return None
    year, month, day = (int(part) for part in match.group(1).split("-"))
    return date(year, month, day)


def is_yearly_period(period: str) -> bool:
    return YEARLY_PERIOD_PATTERN.fullmatch(period) is not None


def yearly_period_from_dates(start: date, end: date) -> str:
    return f"yearly-{start.strftime('%Y-%m')}_{end.strftime('%Y-%m')}"


def yearly_period_bounds(period: str) -> tuple[str, str] | None:
    match = YEARLY_PERIOD_PATTERN.fullmatch(period)
    if match is None:
        return None
    return match.group(1), match.group(2)


def yearly_period_end_month(period: str) -> str:
    bounds = yearly_period_bounds(period)
    if bounds is None:
        return period
    return bounds[1]


def fy_folder_name_for_period(period: str) -> str:
    from networthcsv.utils.path import fy_folder_name

    if is_yearly_period(period):
        return fy_folder_name(yearly_period_end_month(period))
    return fy_folder_name(period)


def covered_months_between(start: date, end: date) -> tuple[str, ...]:
    """Return YYYY-MM covered-month keys from start through end (inclusive)."""
    if end < start:
        return ()
    months: list[str] = []
    current = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    while current <= end_month:
        months.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return tuple(months)


def fiscal_year_key(start: date, end: date) -> str:
    fy_start = start.year if start.month >= 4 else start.year - 1
    fy_end = fy_start + 1
    return f"FY{fy_start % 100:02d}-{fy_end}"


def calendar_year_key(start: date, end: date) -> str:
    _ = end
    return str(start.year)


def year_key_for_period(
    start: date,
    end: date,
    *,
    year_display: YearDisplay,
) -> str:
    if year_display == "fiscal_year":
        return fiscal_year_key(start, end)
    return calendar_year_key(start, end)


def year_key_label(year_key: str, *, year_display: YearDisplay) -> str:
    if year_display == "fiscal_year":
        match = _FISCAL_YEAR_KEY_PATTERN.fullmatch(year_key)
        if match is None:
            return year_key
        start_yy = int(match.group(1))
        end_year = int(match.group(2))
        start_year = (end_year // 100) * 100 + start_yy
        if start_year >= end_year:
            start_year -= 100
        return f"FY {start_year}–{end_year}"
    return year_key


def period_for_year_key(
    year_key: str,
    *,
    year_display: YearDisplay,
) -> tuple[date, date]:
    if year_display == "fiscal_year":
        match = _FISCAL_YEAR_KEY_PATTERN.fullmatch(year_key)
        if match is None:
            raise ValueError(f"invalid fiscal year key: {year_key!r}")
        start_yy = int(match.group(1))
        end_year = int(match.group(2))
        start_year = (end_year // 100) * 100 + start_yy
        if start_year >= end_year:
            start_year -= 100
        return date(start_year, 4, 1), date(end_year, 3, 31)
    match = _CALENDAR_YEAR_KEY_PATTERN.fullmatch(year_key)
    if match is None:
        raise ValueError(f"invalid calendar year key: {year_key!r}")
    year = int(match.group(1))
    return date(year, 1, 1), date(year, 12, 31)


def yearly_period_for_year_key(
    year_key: str,
    *,
    year_display: YearDisplay,
) -> str:
    start, end = period_for_year_key(year_key, year_display=year_display)
    return yearly_period_from_dates(start, end)


def parse_month_year_token(token: str) -> tuple[int, int] | None:
    """Parse APRIL-24 or MARCH-25 style tokens."""
    cleaned = token.strip().upper()
    if "-" not in cleaned:
        return None
    month_name, year_part = cleaned.rsplit("-", 1)
    month = _MONTH_NAMES.get(month_name.lower())
    if month is None:
        return None
    if len(year_part) == 2 and year_part.isdigit():
        year = 2000 + int(year_part)
    elif len(year_part) == 4 and year_part.isdigit():
        year = int(year_part)
    else:
        return None
    return year, month


@dataclass(frozen=True)
class CalendarMonthCell:
    month: int
    year: int
    month_key: str


@dataclass(frozen=True)
class CalendarYearSection:
    year_key: str
    label: str
    months: tuple[CalendarMonthCell, ...]


_FISCAL_MONTH_ORDER = (3, 2, 1, 12, 11, 10, 9, 8, 7, 6, 5, 4)
_CALENDAR_MONTH_ORDER = (12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _fiscal_year_start_year(value: date) -> int:
    return value.year if value.month >= 4 else value.year - 1


def _fiscal_year_key_from_start(start_year: int) -> str:
    return f"FY{start_year % 100:02d}-{start_year + 1}"


def _build_fiscal_year_sections(
    range_start: date,
    range_end: date,
    *,
    year_display: YearDisplay,
) -> tuple[CalendarYearSection, ...]:
    start_fy = _fiscal_year_start_year(range_start)
    end_fy = _fiscal_year_start_year(range_end)
    sections: list[CalendarYearSection] = []
    for fy in range(end_fy, start_fy - 1, -1):
        year_key = _fiscal_year_key_from_start(fy)
        months = tuple(
            CalendarMonthCell(
                month=month,
                year=fy if month >= 4 else fy + 1,
                month_key=_month_key(fy if month >= 4 else fy + 1, month),
            )
            for month in _FISCAL_MONTH_ORDER
        )
        sections.append(
            CalendarYearSection(
                year_key=year_key,
                label=year_key_label(year_key, year_display=year_display),
                months=months,
            )
        )
    return tuple(sections)


def _build_calendar_year_only_sections(
    range_start: date,
    range_end: date,
) -> tuple[CalendarYearSection, ...]:
    sections: list[CalendarYearSection] = []
    for year in range(range_end.year, range_start.year - 1, -1):
        year_key = str(year)
        sections.append(
            CalendarYearSection(
                year_key=year_key,
                label=year_key,
                months=tuple(
                    CalendarMonthCell(
                        month=month,
                        year=year,
                        month_key=_month_key(year, month),
                    )
                    for month in _CALENDAR_MONTH_ORDER
                ),
            )
        )
    return tuple(sections)


def build_calendar_year_sections(
    range_start: date,
    range_end: date,
    *,
    year_display: YearDisplay,
) -> tuple[CalendarYearSection, ...]:
    """Build ordered calendar grid sections between two account dates."""
    if range_end < range_start:
        return ()
    if year_display == "fiscal_year":
        return _build_fiscal_year_sections(
            range_start,
            range_end,
            year_display=year_display,
        )
    return _build_calendar_year_only_sections(range_start, range_end)
