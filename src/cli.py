"""Shared CLI helpers for NetworthCSV entry points."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.utils.alerts.service import build_alert_service
from src.context import RunContext
from src.utils.accounts import iter_accounts
from src.logging_config import configure_logging
from src.settings import ResolvedAccount, Settings, load_settings

__all__ = [
    "load_context",
    "run_stage_main",
]


def load_context() -> RunContext:
    settings = load_settings()
    configure_logging(settings.log_level)
    return RunContext(
        settings=settings,
        alerts=build_alert_service(alerts=settings.alerts),
    )


def run_stage_main(
    *,
    run_account: Callable[[Path, ResolvedAccount, RunContext], None],
    flush_alerts: bool = True,
) -> None:
    """Load config and run a stage for configured account(s)."""
    ctx = load_context()

    def run_for_account(download_dir: Path, account: ResolvedAccount, _settings: Settings) -> None:
        run_account(download_dir, account, ctx)

    iter_accounts(ctx.settings, run_for_account)
    if flush_alerts:
        ctx.alerts.flush()
