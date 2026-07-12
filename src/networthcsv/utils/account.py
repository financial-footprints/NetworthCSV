"""Account identity display helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount


def account_label_from_parts(bank: str, variant: str | None) -> str:
    if variant:
        return f"{bank}/{variant}"
    return bank


def account_label(account: ResolvedAccount) -> str:
    base = account_label_from_parts(account.bank, account.variant)
    return f"{base} ({account.account_number})"
