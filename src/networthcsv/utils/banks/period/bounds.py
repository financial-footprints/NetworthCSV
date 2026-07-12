"""Derive statement period date bounds from bank billing rules."""

from __future__ import annotations

from datetime import date

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import require_account_date_str
from networthcsv.utils.banks import get_handler
from networthcsv.utils.billing_period import approximate_period_start_from_statement_end


def ordered_date_bounds(start: date, end: date) -> tuple[date, date]:
    """Return ``(start, end)`` with inverted ranges corrected."""
    if start > end:
        return end, start
    return start, end


def resolve_period_bounds(
    text: str,
    *,
    account: ResolvedAccount,
) -> tuple[str | None, str | None, bool]:
    handler = get_handler(account.bank, account.variant)
    period_start, period_end = handler.get_statement_period(text)
    if period_start is not None and period_end is not None:
        period_start, period_end = ordered_date_bounds(period_start, period_end)
        return (
            require_account_date_str(period_start),
            require_account_date_str(period_end),
            False,
        )
    if period_end is None:
        return None, None, False
    period_start = approximate_period_start_from_statement_end(period_end)
    return (
        require_account_date_str(period_start),
        require_account_date_str(period_end),
        True,
    )
