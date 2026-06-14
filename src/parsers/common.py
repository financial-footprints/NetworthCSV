"""Shared helpers for bank statement parsers."""

from __future__ import annotations

import logging

from src.core.amounts import dedupe_transactions
from src.core.transactions import Transaction

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LEN = 120


def is_valid_description(
    description: str,
    *,
    reject_substrings: tuple[str, ...] = ("statement period",),
) -> bool:
    if len(description) > MAX_DESCRIPTION_LEN:
        return False
    lower = description.lower()
    return not any(substring in lower for substring in reject_substrings)


def warn_if_empty_text(text: str, source_file: str) -> bool:
    if not text.strip():
        logger.warning("no text in %s", source_file)
        return True
    return False


def finalize_parse(
    transactions: list[Transaction],
    source_file: str,
    *,
    saw_section: bool = True,
    debug_label: str | None = None,
) -> list[Transaction]:
    unique = dedupe_transactions(transactions)
    if debug_label:
        removed = len(transactions) - len(unique)
        logger.info(
            "debug %s: raw=%d unique=%d deduped=%d %s",
            source_file,
            len(transactions),
            len(unique),
            removed,
            debug_label,
        )
    if saw_section and not unique:
        logger.warning("no transactions found in %s", source_file)
    return unique
