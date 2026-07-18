"""Text trimming and sanitization helpers for statement PDFs."""

from __future__ import annotations

import logging
import re

from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService

logger = logging.getLogger(__name__)

END_OF_TRANSACTIONS_TRIM_MARKER = (
    "------------------------------------------------ End of Transactions "
    "------------------------------------------------"
)

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


_SECTION_BOUNDARY_MARKERS = (
    "IMPORTANT INFORMATION",
    "YOUR TRANSACTIONS",
    "STATEMENT SUMMARY",
    "Statement Summary",
    "MOST IMPORTANT TERMS AND CONDITIONS",
    "Domestic Transactions",
    "PREVIOUS STATEMENT DUES",
    "Past Dues",
    "Account Summary",
    "TOTAL AMOUNT DUE",
    "Statement Date",
    "Billing Period",
)


def _purge_marker_section_block(
    text: str,
    marker: str,
    *,
    all_markers: list[str],
) -> str:
    """Drop a short section header line and following lines until a boundary."""
    words = _marker_words(marker)
    if not words or len(words) > 6:
        return text

    start_anchor = " ".join(words)
    boundaries = {start_anchor, *_SECTION_BOUNDARY_MARKERS}
    for other in all_markers:
        if other != marker:
            boundaries.add(other)

    lines = text.split("\n")
    start_idx: int | None = None
    end_idx: int | None = None
    for index, line in enumerate(lines):
        if start_idx is None:
            if start_anchor in line:
                start_idx = index
            continue
        if any(boundary in line for boundary in boundaries):
            end_idx = index
            break

    if start_idx is None:
        return text
    if end_idx is None:
        end_idx = len(lines)

    return _drop_blank_lines("\n".join(lines[:start_idx] + lines[end_idx:]))


def _is_standalone_section_header(line: str, marker: str) -> bool:
    anchor = " ".join(_marker_words(marker))
    if not anchor:
        return False
    stripped = line.strip()
    if stripped.upper() != anchor.upper():
        return False
    letters = [character for character in anchor if character.isalpha()]
    if not letters:
        return False
    uppercase = sum(1 for character in letters if character.isupper())
    return uppercase / len(letters) >= 0.8


def _marker_has_standalone_section_header(text: str, marker: str) -> bool:
    return any(_is_standalone_section_header(line, marker) for line in text.split("\n"))


def purge_drop_sections(text: str, *, drop_sections: list[str] | None = None) -> str:
    """Remove text matching any drop section marker from sanitized statement text."""
    if not drop_sections:
        return text

    result = text
    for marker in drop_sections:
        if _marker_has_standalone_section_header(result, marker):
            updated = _purge_marker_section_block(
                result,
                marker,
                all_markers=drop_sections,
            )
        else:
            updated = result
        if updated == result:
            updated = _purge_marker_regex(result, marker)
        if updated == result:
            updated = _purge_marker_line_block(result, marker)
        if updated == result:
            logger.debug("drop section marker not matched: %r", marker[:80])
        result = updated

    return _drop_blank_lines(result)


def normalize_match_text(text: str) -> str:
    """Collapse whitespace so PDF layout spacing does not break marker checks."""
    return re.sub(r"\s+", " ", text).strip()


def text_contains_present(text: str, text_contains: list[str]) -> bool:
    return any(marker in text for marker in text_contains if marker)


def text_not_contains_violated(text: str, text_not_contains: list[str]) -> bool:
    normalized = normalize_match_text(text)
    return any(
        normalize_match_text(marker) in normalized
        for marker in text_not_contains
        if marker
    )


def statement_text_eligible(
    text: str,
    *,
    text_contains: list[str],
    text_not_contains: list[str],
    is_manual: bool,
) -> bool:
    if not is_manual and text_not_contains_violated(text, text_not_contains):
        return False
    if text_contains and not text_contains_present(text, text_contains):
        return False
    return True


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
