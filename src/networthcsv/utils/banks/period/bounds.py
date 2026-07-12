"""Derive statement period date bounds from bank billing rules."""

from __future__ import annotations

import calendar
from datetime import date

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import require_account_date_str
from networthcsv.utils.banks import get_handler


def period_start_from_end(end: date, start_day: int) -> date:
    """Return period start on start_day of the month before end's month."""
    if end.month == 1:
        prev_year = end.year - 1
        prev_month = 12
    else:
        prev_year = end.year
        prev_month = end.month - 1
    last_day = calendar.monthrange(prev_year, prev_month)[1]
    day = min(start_day, last_day)
    return date(prev_year, prev_month, day)


def period_start_from_previous_month(end: date) -> date:
    """Return period start as (end.day + 1) of the month before *end*."""
    return period_start_from_end(end, end.day + 1)


def resolve_period_bounds(
    text: str,
    *,
    account: ResolvedAccount,
) -> tuple[str | None, str | None, bool]:
    handler = get_handler(account.bank, account.variant)
    period_start, period_end = handler.get_statement_period(text)
    if period_start is not None and period_end is not None:
        if period_start > period_end:
            period_start, period_end = period_end, period_start
        return (
            require_account_date_str(period_start),
            require_account_date_str(period_end),
            False,
        )
    if period_end is None:
        return None, None, False
    period_start = period_start_from_previous_month(period_end)
    return (
        require_account_date_str(period_start),
        require_account_date_str(period_end),
        True,
    )
