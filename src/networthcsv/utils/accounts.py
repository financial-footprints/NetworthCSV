"""Multi-account iteration helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from networthcsv.settings import (
    ResolvedAccount,
    Settings,
    account_download_path,
    accounts_to_run,
)


def iter_accounts(
    settings: Settings,
    fn: Callable[[Path, ResolvedAccount, Settings], None],
) -> None:
    for account in accounts_to_run(settings):
        fn(account_download_path(settings, account), account, settings)
