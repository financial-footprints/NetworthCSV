"""Shared CLI helpers for NetworthCSV entry points."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from pathlib import Path

from networthcsv.utils.alerts.service import build_alert_service
from networthcsv.context import RunContext
from networthcsv.errors import NetworthCsvError
from networthcsv.pipeline.reporter import (
    ConsoleRunReporter,
    NullRunReporter,
    RunReporter,
)
from networthcsv.pipeline.runner import run_stage_for_accounts
from networthcsv.logging import configure_logging
from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    load_settings,
    validate_run_filter,
)

__all__ = [
    "apply_run_overrides",
    "cli_main",
    "load_context",
    "run_global_main",
    "run_stage_main",
]


def apply_run_overrides(
    settings: Settings,
    run_overrides: RunSettings | Mapping[str, object] | None,
) -> Settings:
    if run_overrides is None:
        return settings

    merged = settings.run.model_dump()
    if isinstance(run_overrides, RunSettings):
        patch = run_overrides.model_dump(exclude_none=True)
    else:
        patch = {
            key: value for key, value in run_overrides.items() if value is not None
        }
    merged.update(patch)
    updated = dataclasses.replace(settings, run=RunSettings.model_validate(merged))
    validate_run_filter(updated)
    return updated


def load_context(
    *,
    config_path: str | Path | None = None,
    run_overrides: RunSettings | Mapping[str, object] | None = None,
    reporter: RunReporter | None = None,
) -> RunContext:
    settings = load_settings(config_path)
    settings = apply_run_overrides(settings, run_overrides)
    configure_logging(settings.log_level)
    return RunContext(
        settings=settings,
        alerts=build_alert_service(alerts=settings.alerts),
        reporter=reporter if reporter is not None else NullRunReporter(),
    )


def run_stage_main(
    *,
    run_account: Callable[[RunContext, ResolvedAccount], object],
    flush_alerts: bool = True,
    config_path: str | Path | None = None,
    run_overrides: RunSettings | Mapping[str, object] | None = None,
) -> None:
    """Load config and run a stage for configured account(s)."""
    ctx = load_context(
        config_path=config_path,
        run_overrides=run_overrides,
        reporter=ConsoleRunReporter(),
    )
    run_stage_for_accounts(ctx, run_account)
    if flush_alerts:
        ctx.alerts.flush()


def run_global_main(
    *,
    run: Callable[[RunContext], object],
    flush_alerts: bool = True,
    config_path: str | Path | None = None,
    run_overrides: RunSettings | Mapping[str, object] | None = None,
) -> None:
    """Load config and run a single global stage."""
    ctx = load_context(
        config_path=config_path,
        run_overrides=run_overrides,
        reporter=ConsoleRunReporter(),
    )
    _ = run(ctx)
    if flush_alerts:
        ctx.alerts.flush()


def cli_main(fn: Callable[[], None]) -> None:
    """Run a CLI entry point, mapping library errors to process exit."""
    try:
        fn()
    except NetworthCsvError as exc:
        raise SystemExit(f"error: {exc}") from exc
