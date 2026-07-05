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
    start_marker: str | None = None,
    end_marker: str | None = None,
) -> str:
    """Keep lines from start_marker through end_marker, inclusive of both marker lines."""
    lines = raw.split("\n")
    start_idx = 0

    if start_marker is not None:
        found = next((i for i, line in enumerate(lines) if start_marker in line), None)
        if found is None:
            logger.debug("start_marker not found: %r", start_marker)
        else:
            start_idx = found

    end_idx = len(lines)
    if end_marker is not None:
        found = next(
            (
                i
                for i, line in enumerate(lines[start_idx:], start=start_idx)
                if end_marker in line
            ),
            None,
        )
        if found is None:
            if any(end_marker in line for line in lines):
                return ""
            logger.debug("end_marker not found: %r", end_marker)
        else:
            end_idx = found + 1

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


def purge_information_markers(
    text: str, *, information_markers: list[str] | None = None
) -> str:
    """Remove text matching any information marker from sanitized statement text."""
    if not information_markers:
        return text

    result = text
    for marker in information_markers:
        updated = _purge_marker_regex(result, marker)
        if updated == result:
            updated = _purge_marker_line_block(result, marker)
        if updated == result:
            logger.debug("information marker not matched: %r", marker[:80])
        result = updated

    return _drop_blank_lines(result)


def file_marker_present(text: str, file_marker: str) -> bool:
    return file_marker in text


def check_file_marker(
    text: str,
    *,
    file_marker: str,
    source_file: str,
    account_label: str,
    alerts: AlertService | None = None,
) -> bool:
    if file_marker_present(text, file_marker):
        return True
    logger.debug(
        "ignored %s for %s: file marker %r not found",
        source_file,
        account_label,
        file_marker,
    )
    if alerts is not None:
        alerts.emit(
            Alert(
                kind=AlertKind.FILE_MARKER_MISSING,
                message=f"file marker {file_marker!r} not found in {source_file}",
                account=account_label,
                source_file=source_file,
                file_marker=file_marker,
            )
        )
    return False
