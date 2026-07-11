"""Extract statement dates from credit card statement text."""

from __future__ import annotations

import logging
from datetime import date

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.month_stem import month_stem_from_filename

logger = logging.getLogger(__name__)

__all__ = [
    "extract_statement_date",
    "extract_statement_period",
    "resolve_month_stem",
]


def extract_statement_date(text: str, *, account: ResolvedAccount) -> date | None:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_date(text)


def extract_statement_period(
    text: str, *, account: ResolvedAccount
) -> tuple[date | None, date | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_period(text)


def resolve_month_stem(text: str, filename: str, *, account: ResolvedAccount) -> str:
    handler = get_handler(account.bank, account.variant)
    parsed = handler.get_statement_date(text)
    if parsed is not None:
        return parsed.strftime("%Y-%m")
    fallback = month_stem_from_filename(filename)
    if fallback != "unknown-month":
        logger.debug(
            "statement date not found in %s; using filename month %s",
            filename,
            fallback,
        )
    return fallback
