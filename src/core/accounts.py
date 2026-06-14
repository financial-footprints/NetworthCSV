"""Multi-account iteration for CLI entry points."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.settings import AccountSettings, Settings, account_download_path, account_for_download_dir


def iter_accounts(
    settings: Settings,
    fn: Callable[[Path, AccountSettings, Settings], None],
    *,
    download_dir: Path | None = None,
) -> None:
    if download_dir is not None:
        account = account_for_download_dir(settings, download_dir)
        fn(download_dir, account, settings)
        return

    for index, account in enumerate(settings.accounts):
        if index > 0:
            print()
        if len(settings.accounts) > 1:
            print(f"=== {account.bank} ===")
            print()
        fn(account_download_path(settings, account), account, settings)
