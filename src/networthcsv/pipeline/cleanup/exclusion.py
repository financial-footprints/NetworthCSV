"""Statement exclusion checks for cleanup."""

from __future__ import annotations

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.text import text_not_contains_violated


def statement_should_exclude(
    raw: str,
    sanitized: str,
    *,
    account: ResolvedAccount,
    is_manual: bool,
) -> bool:
    """Return True when a staging statement must be deleted (non-statement attachment)."""
    if is_manual:
        return False

    markers = account.statement.text_not_contains
    return text_not_contains_violated(raw, markers) or text_not_contains_violated(
        sanitized, markers
    )
