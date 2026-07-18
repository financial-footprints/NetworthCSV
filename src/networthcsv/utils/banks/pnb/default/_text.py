"""Shared text preparation helpers for PNB layout handlers."""

from __future__ import annotations

from networthcsv.utils.banks.helpers.text import (
    purge_drop_sections,
    sanitize_statement_text,
    trim_by_markers,
)
from networthcsv.utils.banks.pnb.common import DROP_SECTIONS, TRIM_END


def prepare_statement_text(
    raw: str,
    *,
    trim_start: list[str],
) -> str:
    trimmed = trim_by_markers(
        raw,
        trim_start=trim_start,
        trim_end=TRIM_END,
    )
    sanitized = sanitize_statement_text(trimmed)
    return purge_drop_sections(sanitized, drop_sections=DROP_SECTIONS)


def trim_statement_body(raw: str, *, trim_start: list[str]) -> str:
    return trim_by_markers(
        raw,
        trim_start=trim_start,
        trim_end=TRIM_END,
    )
