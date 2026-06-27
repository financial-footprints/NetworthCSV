"""Extract statement dates from credit card statement text."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from networthcsv.settings import (
    ContextRangeMarker,
    LabelNextLineMarker,
    LabelRangeMarker,
    LabelSingleMarker,
    ResolvedAccount,
    StatementDateMarker,
    TopRangeMarker,
)

logger = logging.getLogger(__name__)

_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")

_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%b/%Y",
    "%d %b, %Y",
    "%d %b %Y",
    "%d %B, %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
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


def month_stem_from_name(filename: str) -> str:
    match = _DATE_IN_NAME.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"


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


def _label_regex(label: str) -> re.Pattern[str]:
    words = label.split()
    body = r"\s+".join(_word_pattern(word) for word in words if word.strip())
    return re.compile(body, re.IGNORECASE)


def _first_date_in_text(text: str) -> date | None:
    for match in _DATE_CANDIDATE.finditer(text):
        parsed = parse_date_string(match.group(0))
        if parsed is not None:
            return parsed
    return None


def _last_date_in_text(text: str) -> date | None:
    last: date | None = None
    for match in _DATE_CANDIDATE.finditer(text):
        parsed = parse_date_string(match.group(0))
        if parsed is not None:
            last = parsed
    return last


def _parse_range_remainder(remainder: str, *, joiners: tuple[str, ...]) -> date | None:
    for joiner in joiners:
        if joiner not in remainder:
            continue
        left, _, right = remainder.partition(joiner)
        left_date = _last_date_in_text(left)
        right_date = _first_date_in_text(right)
        if left_date is not None and right_date is not None:
            return right_date
    return _first_date_in_text(remainder)


def _take_from_range(left: str, right: str, *, take: str) -> date | None:
    left_date = _last_date_in_text(left)
    right_date = _first_date_in_text(right)
    if left_date is None or right_date is None:
        return None
    if take == "start":
        return left_date
    return right_date


def _find_label(text: str, label: str, *, limit: int = 4000) -> re.Match[str] | None:
    return _label_regex(label).search(text[:limit])


def _line_after_label(text: str, label: str, *, limit: int = 4000) -> str | None:
    match = _find_label(text, label, limit=limit)
    if match is None:
        return None
    start = match.end()
    slice_end = min(len(text), start + limit)
    tail = text[start:slice_end]
    line_break = tail.find("\n")
    if line_break == -1:
        return None
    remainder = tail[line_break + 1 :]
    for line in remainder.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _apply_label_single(text: str, marker: LabelSingleMarker) -> date | None:
    match = _find_label(text, marker.label)
    if match is None:
        return None
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    label_end_in_line = match.end() - line_start
    remainder = line[label_end_in_line:]
    return _parse_range_remainder(remainder, joiners=_RANGE_JOINERS)


def _apply_label_next_line(text: str, marker: LabelNextLineMarker) -> date | None:
    next_line = _line_after_label(text, marker.label)
    if next_line is None:
        return None
    return _parse_range_remainder(next_line, joiners=_RANGE_JOINERS)


def _apply_label_range(text: str, marker: LabelRangeMarker) -> date | None:
    match = _find_label(text, marker.label)
    if match is None:
        return None
    remainder = text[match.end() : match.end() + 300]
    if marker.joiner not in remainder:
        return None
    left, _, right = remainder.partition(marker.joiner)
    return _take_from_range(left, right, take=marker.take)


def _apply_context_range(text: str, marker: ContextRangeMarker) -> date | None:
    context_pattern = re.compile(re.escape(marker.context), re.IGNORECASE)
    for context_match in context_pattern.finditer(text[:4000]):
        start = max(0, context_match.start() - 250)
        end = min(len(text), context_match.end() + 500)
        window = text[start:end]
        joiner_pattern = re.compile(re.escape(marker.joiner), re.IGNORECASE)
        for joiner_match in joiner_pattern.finditer(window):
            left = window[max(0, joiner_match.start() - 80) : joiner_match.start()]
            right = window[joiner_match.end() : joiner_match.end() + 80]
            parsed = _take_from_range(left, right, take=marker.take)
            if parsed is not None:
                return parsed
    return None


def _apply_top_range(text: str, marker: TopRangeMarker) -> date | None:
    haystack = text[: marker.search_chars]
    joiner_pattern = re.compile(re.escape(marker.joiner))
    for joiner_match in joiner_pattern.finditer(haystack):
        left = haystack[max(0, joiner_match.start() - 80) : joiner_match.start()]
        right = haystack[joiner_match.end() : joiner_match.end() + 80]
        parsed = _take_from_range(left, right, take=marker.take)
        if parsed is not None:
            return parsed
    return None


def _apply_marker(text: str, marker: StatementDateMarker) -> date | None:
    if isinstance(marker, LabelSingleMarker):
        return _apply_label_single(text, marker)
    if isinstance(marker, LabelNextLineMarker):
        return _apply_label_next_line(text, marker)
    if isinstance(marker, LabelRangeMarker):
        return _apply_label_range(text, marker)
    if isinstance(marker, ContextRangeMarker):
        return _apply_context_range(text, marker)
    if isinstance(marker, TopRangeMarker):
        return _apply_top_range(text, marker)
    return None


def extract_statement_date(text: str, *, account: ResolvedAccount) -> date | None:
    for marker in account.statement_date_markers:
        parsed = _apply_marker(text, marker)
        if parsed is not None:
            return parsed
    return None


def resolve_month_stem(text: str, filename: str, *, account: ResolvedAccount) -> str:
    parsed = extract_statement_date(text, account=account)
    if parsed is not None:
        return parsed.strftime("%Y-%m")
    fallback = month_stem_from_name(filename)
    if fallback != "unknown-month":
        logger.debug(
            "statement date not found in %s; using filename month %s",
            filename,
            fallback,
        )
    return fallback
