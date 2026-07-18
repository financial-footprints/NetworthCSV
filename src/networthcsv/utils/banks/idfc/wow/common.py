"""Shared IDFC WOW layout detection helpers."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.amounts import first_amount_in_text
from networthcsv.utils.banks.helpers.dates import find_label, label_regex

_INLINE_HEADER_ROW = re.compile(
    r"Total Amount Due.*Minimum Amount Due.*Credit Limit",
    re.IGNORECASE,
)

_STACKED_BOUNDARY = re.compile(
    r"Minimum Amount Due|^\+$|^-$|^=$",
    re.IGNORECASE,
)


def is_stacked_boundary(line: str) -> bool:
    """Return True when a line ends the stacked summary window."""
    stripped = line.strip()
    if _INLINE_HEADER_ROW.search(stripped):
        return False
    return bool(_STACKED_BOUNDARY.search(stripped))


def has_inline_summary_header(text: str) -> bool:
    return _INLINE_HEADER_ROW.search(text) is not None


def is_standalone_opening_balance_line(line: str) -> bool:
    stripped = line.strip()
    if label_regex("Opening Balance").search(stripped) is None:
        return False
    return first_amount_in_text(line) is None
