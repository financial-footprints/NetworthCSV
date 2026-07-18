"""Statement period identifiers for monthly and annual statements.

Monthly statements use ``YYYY-MM`` (e.g. ``2024-04``).
Annual statements use fiscal year keys (e.g. ``FY24-2025``) or calendar years
(``2024``) depending on bank configuration.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

YearDisplay = Literal["fiscal_year", "calendar_year"]

MONTH_PERIOD_PATTERN = re.compile(r"^(\d{4}-\d{2})$")
FILENAME_MONTH_PATTERN = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")
_STAGING_EMAIL_DATE_PATTERN = re.compile(
    r"__(\d{4}-\d{2}-\d{2})(?:__annual)?(?:\s+\(\d+\))?\.(?:pdf|csv)$",
    re.IGNORECASE,
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


def is_fy_period(period: str) -> bool:
    """True when *period* is an Indian fiscal year key such as ``FY24-2025``."""
    return _FISCAL_YEAR_KEY_PATTERN.fullmatch(period) is not None


def is_calendar_year_period(period: str) -> bool:
    """True when *period* is a four-digit calendar year key."""
    return _CALENDAR_YEAR_KEY_PATTERN.fullmatch(period) is not None


def is_annual_period(period: str) -> bool:
    """True when *period* identifies an annual (fiscal or calendar year) statement."""
    return is_fy_period(period) or is_calendar_year_period(period)


def month_period_from_filename(filename: str) -> str:
    """Extract ``YYYY-MM`` from a filename, or ``unknown-month`` if not found."""
    match = FILENAME_MONTH_PATTERN.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"


def email_date_from_staging_filename(filename: str) -> date | None:
    """Return the email received date encoded in a staging PDF/CSV name, if present."""
    name = Path(filename).name
    match = _STAGING_EMAIL_DATE_PATTERN.search(name)
    if match is None:
        return None
    year, month, day = (int(part) for part in match.group(1).split("-"))
    return date(year, month, day)


def staging_filename_is_annual(filename: str) -> bool:
    """True when staging filename was marked annual at extract time."""
    name = Path(filename).name.lower()
    return "__annual." in name or "__annual " in name


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def fy_period_bounds(
    fy_key: str,
    *,
    year_display: YearDisplay = "fiscal_year",
) -> tuple[date, date]:
    """Return inclusive Apr–Mar (or calendar-year) bounds for an annual period key."""
    return period_for_year_key(fy_key, year_display=year_display)


def calendar_bounds_for_period_key(period: str) -> tuple[date, date] | None:
    """Return inclusive calendar bounds for a monthly or annual period key."""
    month_period = parse_month_period(period)
    if month_period is not None:
        year_str, month_str = month_period.split("-", 1)
        year, month = int(year_str), int(month_str)
        return (
            date(year, month, 1),
            date(year, month, _last_day_of_month(year, month)),
        )

    if is_annual_period(period):
        try:
            return fy_period_bounds(period)
        except ValueError:
            return None
    return None


def _fiscal_year_key_from_month_key(month_key: str) -> str:
    year_str, month_str = month_key.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    fy_start, fy_end = (year, year + 1) if month >= 4 else (year - 1, year)
    return f"FY{fy_start % 100:02d}-{fy_end}"


def fy_key_from_dates(start: date, end: date) -> str:
    """Map an annual statement date span to its Indian fiscal year key."""
    if end < start:
        start, end = end, start
    months = covered_months_between(start, end)
    if not months:
        return fiscal_year_key(start, end)
    fy_counts: dict[str, int] = {}
    for month_key in months:
        fy = _fiscal_year_key_from_month_key(month_key)
        fy_counts[fy] = fy_counts.get(fy, 0) + 1
    return max(fy_counts, key=lambda fy: fy_counts[fy])


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


def _year_key_for_month_key(month_key: str, *, year_display: YearDisplay) -> str:
    if year_display == "fiscal_year":
        return _fiscal_year_key_from_month_key(month_key)
    year_str, _ = month_key.split("-", 1)
    return year_str


def _month_cell(month_key: str) -> CalendarMonthCell:
    year_str, month_str = month_key.split("-", 1)
    return CalendarMonthCell(
        month=int(month_str),
        year=int(year_str),
        month_key=month_key,
    )


def build_calendar_year_sections(
    start: date,
    end: date,
    *,
    year_display: YearDisplay = "fiscal_year",
) -> tuple[CalendarYearSection, ...]:
    """Build full year grids for each year overlapping *start* through *end*.

    Sections are ordered newest-first (e.g. 2026, then 2025, then 2024).
    Months within each section are ordered newest-first (e.g. December, then
    November, …, then January).
    """
    if end < start:
        return ()

    year_keys: list[str] = []
    seen: set[str] = set()
    for month_key in covered_months_between(start, end):
        year_key = _year_key_for_month_key(month_key, year_display=year_display)
        if year_key in seen:
            continue
        seen.add(year_key)
        year_keys.append(year_key)
    year_keys.reverse()

    sections: list[CalendarYearSection] = []
    for year_key in year_keys:
        period_start, period_end = period_for_year_key(
            year_key,
            year_display=year_display,
        )
        months = tuple(
            _month_cell(month_key)
            for month_key in reversed(
                covered_months_between(period_start, period_end)
            )
        )
        sections.append(
            CalendarYearSection(
                year_key=year_key,
                label=year_key_label(year_key, year_display=year_display),
                months=months,
            )
        )
    return tuple(sections)
