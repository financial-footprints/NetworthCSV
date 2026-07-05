"""Text processing helpers for statement PDFs."""

from __future__ import annotations

import logging
import re

from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService

logger = logging.getLogger(__name__)

_DISALLOWED = re.compile(r"[^A-Za-z0-9 \n\r.,/\-:()%&@#*+=<>|_$]")


def _normalize_line(line: str) -> str:
    line = line.replace("\t", " ")
    return line.rstrip()


def sanitize_statement_text(raw: str) -> str:
    cleaned = _DISALLOWED.sub(" ", raw)
    return "\n".join(_normalize_line(line) for line in cleaned.split("\n"))


def trim_by_markers(
    raw: str,
    *,
    trim_start: list[str] | None = None,
    trim_end: list[str] | None = None,
) -> str:
    """Keep lines from trim_start through trim_end, inclusive of marker lines."""
    start = list(trim_start) if trim_start else []
    end = list(trim_end) if trim_end else []

    lines = raw.split("\n")
    start_idx = 0

    if start:
        found_indices = [
            index
            for index, line in enumerate(lines)
            if any(marker in line for marker in start)
        ]
        if not found_indices:
            logger.debug("trim_start not found: %r", start)
        else:
            start_idx = min(found_indices)

    end_idx = len(lines)
    if end:
        found_indices = [
            index
            for index, line in enumerate(lines[start_idx:], start=start_idx)
            if any(marker in line for marker in end)
        ]
        if not found_indices:
            if any(marker in line for line in lines for marker in end):
                return ""
            logger.debug("trim_end not found: %r", end)
        else:
            end_idx = max(found_indices) + 1

    if start_idx >= end_idx:
        return ""

    return "\n".join(lines[start_idx:end_idx])


def _marker_words(marker: str) -> list[str]:
    return re.sub(r"\s+", " ", marker.strip()).split()


def _information_marker_pattern(marker: str) -> re.Pattern[str]:
    words = _marker_words(marker)
    if not words:
        return re.compile(r"(?!)", re.DOTALL)
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(body, re.DOTALL)


def _drop_blank_lines(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if line.strip())


def _purge_marker_regex(text: str, marker: str) -> str:
    return _information_marker_pattern(marker).sub("", text)


def _start_anchor(words: list[str]) -> str:
    if len(words) <= 6:
        return " ".join(words)
    first = words[0].lstrip("*")
    return " ".join([first, *words[1:5]])


def _purge_marker_line_block(text: str, marker: str) -> str:
    """Remove lines from the first start anchor through the last end anchor."""
    words = _marker_words(marker)
    if not words:
        return text

    if len(words) <= 6:
        start_anchors = [" ".join(words)]
        end_anchor = start_anchors[0]
    else:
        start_anchors = [_start_anchor(words)]
        end_anchor = " ".join(words[-4:])

    lines = text.split("\n")
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and any(anchor in line for anchor in start_anchors):
            start_idx = i
        if start_idx is not None and end_anchor in line:
            end_idx = i

    if start_idx is None or end_idx is None or start_idx > end_idx:
        return text

    return _drop_blank_lines("\n".join(lines[:start_idx] + lines[end_idx + 1 :]))


def purge_drop_sections(text: str, *, drop_sections: list[str] | None = None) -> str:
    """Remove text matching any drop section marker from sanitized statement text."""
    if not drop_sections:
        return text

    result = text
    for marker in drop_sections:
        updated = _purge_marker_regex(result, marker)
        if updated == result:
            updated = _purge_marker_line_block(result, marker)
        if updated == result:
            logger.debug("drop section marker not matched: %r", marker[:80])
        result = updated

    return _drop_blank_lines(result)


def text_contains_present(text: str, text_contains: list[str]) -> bool:
    return any(marker in text for marker in text_contains if marker)


def check_text_contains(
    text: str,
    *,
    text_contains: list[str],
    source_file: str,
    account_label: str,
    alerts: AlertService | None = None,
) -> bool:
    if text_contains_present(text, text_contains):
        return True
    logger.debug(
        "ignored %s for %s: text_contains %r not found",
        source_file,
        account_label,
        text_contains,
    )
    if alerts is not None:
        alerts.emit(
            Alert(
                kind=AlertKind.TEXT_CONTAINS_MISSING,
                message=f"text_contains {text_contains!r} not found in {source_file}",
                account=account_label,
                source_file=source_file,
                text_contains=text_contains,
            )
        )
    return False
