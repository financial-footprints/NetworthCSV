"""Resolve statement period keys (YYYY-MM, FY…) from bank statement text."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.base import BankHandler
from networthcsv.utils.statement_period import (
    fy_key_from_dates,
    month_period_from_filename,
)

logger = logging.getLogger(__name__)

PeriodSource = Literal[
    "annual", "content_date", "filename_fallback", "manual", "unknown"
]

__all__ = [
    "PeriodSource",
    "extract_statement_date",
    "extract_statement_period",
    "resolve_period_key",
    "resolve_period_key_with_source",
]


def extract_statement_date(text: str, *, account: ResolvedAccount) -> date | None:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_date(text)


def extract_statement_period(
    text: str, *, account: ResolvedAccount
) -> tuple[date | None, date | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_period(text)


def _annual_period_with_source(
    handler: BankHandler, text: str
) -> tuple[str, PeriodSource] | None:
    if not handler.is_annual_statement(text):
        return None
    period = handler.get_annual_period(text)
    if period is None:
        return None
    return fy_key_from_dates(period[0], period[1]), "annual"


def _resolve_monthly_period_with_source(
    handler: BankHandler, text: str, filename: str
) -> tuple[str, PeriodSource]:
    parsed = handler.get_statement_date(text)
    if parsed is not None:
        return parsed.strftime("%Y-%m"), "content_date"
    fallback = month_period_from_filename(filename)
    if fallback != "unknown-month":
        logger.debug(
            "statement date not found in %s; using filename month %s",
            filename,
            fallback,
        )
        return fallback, "filename_fallback"
    return "unknown-month", "unknown"


def resolve_period_key_with_source(
    text: str, filename: str, *, account: ResolvedAccount
) -> tuple[str, PeriodSource]:
    handler = get_handler(account.bank, account.variant)
    if handler.is_annual_statement(text):
        annual = _annual_period_with_source(handler, text)
        if annual is not None:
            return annual
        logger.warning("annual statement in %s but period not found", filename)
        return "unknown-month", "unknown"
    return _resolve_monthly_period_with_source(handler, text, filename)


def resolve_period_key(text: str, filename: str, *, account: ResolvedAccount) -> str:
    period, _source = resolve_period_key_with_source(text, filename, account=account)
    return period
