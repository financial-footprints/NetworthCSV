"""Extract statement dates from credit card statement text."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.statement_period import (
    month_period_from_filename,
    yearly_period_from_dates,
)

logger = logging.getLogger(__name__)

PeriodSource = Literal[
    "yearly", "content_date", "filename_fallback", "manual", "unknown"
]

__all__ = [
    "PeriodSource",
    "extract_statement_date",
    "extract_statement_period",
    "resolve_month_period",
    "resolve_month_period_with_source",
    "resolve_statement_period",
    "resolve_statement_period_with_source",
]


def extract_statement_date(text: str, *, account: ResolvedAccount) -> date | None:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_date(text)


def extract_statement_period(
    text: str, *, account: ResolvedAccount
) -> tuple[date | None, date | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_statement_period(text)


def resolve_month_period_with_source(
    text: str, filename: str, *, account: ResolvedAccount
) -> tuple[str, PeriodSource]:
    handler = get_handler(account.bank, account.variant)
    if handler.is_yearly_statement(text):
        period = handler.get_yearly_period(text)
        if period is not None:
            return yearly_period_from_dates(period[0], period[1]), "yearly"
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


def resolve_statement_period_with_source(
    text: str, filename: str, *, account: ResolvedAccount
) -> tuple[str, PeriodSource]:
    handler = get_handler(account.bank, account.variant)
    if handler.is_yearly_statement(text):
        period = handler.get_yearly_period(text)
        if period is not None:
            return yearly_period_from_dates(period[0], period[1]), "yearly"
        logger.warning("yearly statement in %s but period not found", filename)
        return "unknown-month", "unknown"
    return resolve_month_period_with_source(text, filename, account=account)


def resolve_statement_period(
    text: str, filename: str, *, account: ResolvedAccount
) -> str:
    period, _source = resolve_statement_period_with_source(
        text, filename, account=account
    )
    return period


def resolve_month_period(text: str, filename: str, *, account: ResolvedAccount) -> str:
    period, _source = resolve_month_period_with_source(text, filename, account=account)
    return period
