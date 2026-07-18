"""Statement date parsing and label search helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from functools import lru_cache

_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%b/%Y",
    "%d/%b/%y",
    "%d %b, %Y",
    "%d %b %Y",
    "%d %b %y",
    "%d %B, %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
)

_RANGE_JOINERS = (" to ", " - ", " To ")

_DATE_CANDIDATE = re.compile(
    r"(?:"
    r"\d{1,2}/\d{1,2}/\d{4}|"
    r"\d{1,2}-\d{1,2}-\d{4}|"
    r"\d{1,2}/[A-Za-z]{3}/\d{4}|"
    r"\d{1,2}-[A-Za-z]{3}-\d{4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}|"
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}"
    r")",
    re.IGNORECASE,
)

# PDF text extraction sometimes splits the day digit: ``1 6-MAR-2024``.
_SPACED_DAY_BEFORE_MONTH = re.compile(
    r"(\d)\s+(\d-[A-Za-z]{3}-\d{4})",
    re.IGNORECASE,
)


def normalize_spaced_date_text(text: str) -> str:
    """Collapse split day digits before month-abbrev dates (e.g. ``1 6-MAR-2024``)."""
    return _SPACED_DAY_BEFORE_MONTH.sub(r"\1\2", text)


def parse_date_string(value: str) -> date | None:
    stripped = value.strip().rstrip(",")
    if not stripped:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def _word_pattern(word: str) -> str:
    word = word.strip()
    if not word:
        return ""
    if word.isalpha():
        return "".join(f"{re.escape(ch)}+\\s*" for ch in word).rstrip("\\s*")
    return re.escape(word)


@lru_cache(maxsize=256)
def label_regex(label: str) -> re.Pattern[str]:
    words = label.split()
    body = r"\s+".join(_word_pattern(word) for word in words if word.strip())
    return re.compile(body, re.IGNORECASE)


def find_label(text: str, label: str, *, limit: int = 4000) -> re.Match[str] | None:
    return label_regex(label).search(text[:limit])


def first_date_in_text(text: str) -> date | None:
    normalized = normalize_spaced_date_text(text)
    for match in _DATE_CANDIDATE.finditer(normalized):
        parsed = parse_date_string(match.group(0))
        if parsed is not None:
            return parsed
    return None


def last_date_in_text(text: str) -> date | None:
    normalized = normalize_spaced_date_text(text)
    last: date | None = None
    for match in _DATE_CANDIDATE.finditer(normalized):
        parsed = parse_date_string(match.group(0))
        if parsed is not None:
            last = parsed
    return last


def parse_range_bounds(
    remainder: str, *, joiners: tuple[str, ...] = _RANGE_JOINERS
) -> tuple[date | None, date | None]:
    for joiner in joiners:
        if joiner not in remainder:
            continue
        left, _, right = remainder.partition(joiner)
        left_date = last_date_in_text(left)
        right_date = first_date_in_text(right)
        if left_date is not None and right_date is not None:
            return left_date, right_date
    single = first_date_in_text(remainder)
    return None, single


def take_from_range(left: str, right: str, *, take: str) -> date | None:
    left_date = last_date_in_text(left)
    right_date = first_date_in_text(right)
    if left_date is None or right_date is None:
        return None
    if take == "start":
        return left_date
    return right_date


def bounds_from_joiner(left: str, right: str) -> tuple[date | None, date | None]:
    return (
        take_from_range(left, right, take="start"),
        take_from_range(left, right, take="end"),
    )


def line_remainder_after_label(text: str, label: str) -> str | None:
    match = find_label(text, label)
    if match is None:
        return None
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    label_end_in_line = match.end() - line_start
    return line[label_end_in_line:]


def date_after_label(text: str, label: str, *, limit: int = 4000) -> date | None:
    match = find_label(text, label, limit=limit)
    if match is None:
        return None
    remainder = line_remainder_after_label(text, label)
    if remainder is not None and remainder.strip():
        _, end = parse_range_bounds(remainder)
        if end is not None:
            return end
    start = match.end()
    slice_end = min(len(text), start + limit)
    tail = text[start:slice_end]
    line_break = tail.find("\n")
    search_text = tail if line_break == -1 else tail[line_break + 1 :]
    for line in search_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        parsed = first_date_in_text(stripped)
        if parsed is not None:
            return parsed
    return None


def label_single_date_end(text: str, label: str) -> date | None:
    remainder = line_remainder_after_label(text, label)
    if remainder is None:
        return None
    _, end = parse_range_bounds(remainder)
    return end


def label_range_period(
    text: str, label: str, joiner: str
) -> tuple[date | None, date | None]:
    match = find_label(text, label)
    if match is None:
        return None, None
    remainder = text[match.end() : match.end() + 300]
    if joiner not in remainder:
        return None, None
    left, _, right = remainder.partition(joiner)
    return bounds_from_joiner(left, right)


def label_range_end(text: str, label: str, joiner: str) -> date | None:
    _, end = label_range_period(text, label, joiner)
    return end


def context_range_period(
    text: str, context: str, joiner: str
) -> tuple[date | None, date | None]:
    context_pattern = re.compile(re.escape(context), re.IGNORECASE)
    for context_match in context_pattern.finditer(text[:4000]):
        start = max(0, context_match.start() - 250)
        end_pos = min(len(text), context_match.end() + 500)
        window = text[start:end_pos]
        joiner_pattern = re.compile(re.escape(joiner), re.IGNORECASE)
        for joiner_match in joiner_pattern.finditer(window):
            left = window[max(0, joiner_match.start() - 80) : joiner_match.start()]
            right = window[joiner_match.end() : joiner_match.end() + 80]
            period_start, period_end = bounds_from_joiner(left, right)
            if period_start is not None and period_end is not None:
                return period_start, period_end
    return None, None


def context_range_end(text: str, context: str, joiner: str) -> date | None:
    _, end = context_range_period(text, context, joiner)
    if end is not None:
        return end
    context_pattern = re.compile(re.escape(context), re.IGNORECASE)
    for context_match in context_pattern.finditer(text[:4000]):
        start = max(0, context_match.start() - 250)
        end_pos = min(len(text), context_match.end() + 500)
        window = text[start:end_pos]
        joiner_pattern = re.compile(re.escape(joiner), re.IGNORECASE)
        for joiner_match in joiner_pattern.finditer(window):
            left = window[max(0, joiner_match.start() - 80) : joiner_match.start()]
            right = window[joiner_match.end() : joiner_match.end() + 80]
            parsed = take_from_range(left, right, take="end")
            if parsed is not None:
                return parsed
    return None


def top_range_period(
    text: str, joiner: str, *, search_chars: int = 2000
) -> tuple[date | None, date | None]:
    haystack = text[:search_chars]
    joiner_pattern = re.compile(re.escape(joiner))
    for joiner_match in joiner_pattern.finditer(haystack):
        left = haystack[max(0, joiner_match.start() - 80) : joiner_match.start()]
        right = haystack[joiner_match.end() : joiner_match.end() + 80]
        period_start, period_end = bounds_from_joiner(left, right)
        if period_start is not None and period_end is not None:
            return period_start, period_end
    return None, None


def top_range_end(text: str, joiner: str, *, search_chars: int = 2000) -> date | None:
    _, end = top_range_period(text, joiner, search_chars=search_chars)
    if end is not None:
        return end
    haystack = text[:search_chars]
    joiner_pattern = re.compile(re.escape(joiner))
    for joiner_match in joiner_pattern.finditer(haystack):
        left = haystack[max(0, joiner_match.start() - 80) : joiner_match.start()]
        right = haystack[joiner_match.end() : joiner_match.end() + 80]
        parsed = take_from_range(left, right, take="end")
        if parsed is not None:
            return parsed
    return None


def first_not_none_date(*values: date | None) -> date | None:
    for value in values:
        if value is not None:
            return value
    return None
