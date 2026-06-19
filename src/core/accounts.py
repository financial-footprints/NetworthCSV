"""Multi-account iteration for CLI entry points."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.settings import (
    ResolvedAccount,
    Settings,
    account_download_path,
    account_label,
    accounts_to_run,
)


def iter_accounts(
    settings: Settings,
    fn: Callable[[Path, ResolvedAccount, Settings], None],
) -> None:
    selected = accounts_to_run(settings)
    for index, account in enumerate(selected):
        if index > 0:
            print()
        if len(selected) > 1:
            print(f"=== {account_label(account)} ===")
            print()
        fn(account_download_path(settings, account), account, settings)
