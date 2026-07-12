"""Resolve statement period keys from bank CSV statement content."""

from __future__ import annotations

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.period.key import PeriodSource

__all__ = ["resolve_csv_period_key_with_source"]


def resolve_csv_period_key_with_source(
    csv_text: str,
    filename: str,
    *,
    account: ResolvedAccount,
) -> tuple[str, PeriodSource]:
    handler = get_handler(account.bank, account.variant)
    return handler.resolve_csv_period_key_with_source(
        csv_text, filename, account=account
    )
