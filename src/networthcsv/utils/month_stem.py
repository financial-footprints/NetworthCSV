"""Shared YYYY-MM month stem helpers."""

from __future__ import annotations

import re

MONTH_STEM_PATTERN = re.compile(r"^(\d{4}-\d{2})$")
FILENAME_MONTH_PATTERN = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")


def month_stem_from_stem(stem: str) -> str | None:
    match = MONTH_STEM_PATTERN.fullmatch(stem)
    if match is None:
        return None
    return match.group(1)


def month_stem_from_filename(filename: str) -> str:
    match = FILENAME_MONTH_PATTERN.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"
