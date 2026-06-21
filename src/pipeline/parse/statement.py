"""Parse sanitized statement text files into transactions."""

from __future__ import annotations

import logging

from src.utils.transactions import Transaction

logger = logging.getLogger(__name__)


def parse_statement_text(text: str, *, source_file: str) -> list[Transaction]:
    """Parse a sanitized statement .txt file into transaction rows."""
    if not text.strip():
        logger.warning("no text in %s", source_file)
        return []
    return []
