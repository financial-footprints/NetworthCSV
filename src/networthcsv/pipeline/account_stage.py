"""Shared per-account stage loop for pipeline orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from networthcsv.context import RunContext
from networthcsv.errors import raise_if_cancelled
from networthcsv.settings import ResolvedAccount

T = TypeVar("T")


def _report_account_banner(
    ctx: RunContext, account: ResolvedAccount, index: int, total: int
) -> None:
    ctx.reporter.account_banner(account, index=index, total=total)


def _run_account_stage(
    ctx: RunContext,
    run_account: Callable[[RunContext, ResolvedAccount], T],
) -> tuple[T, ...]:
    selected = ctx.settings.accounts_to_run()
    results: list[T] = []
    for index, account in enumerate(selected):
        raise_if_cancelled(ctx)
        if index > 0:
            ctx.reporter.blank_line()
        _report_account_banner(ctx, account, index, len(selected))
        results.append(run_account(ctx, account))
    return tuple(results)
