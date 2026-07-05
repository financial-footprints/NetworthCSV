"""Pipeline orchestration for extract, cleanup, and parse stages."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from networthcsv.context import RunContext
from networthcsv.pipeline.cleanup import cleanup as cleanup_stage
from networthcsv.pipeline.get_statements import extract as extract_stage
from networthcsv.pipeline.metadata import metadata as metadata_stage
from networthcsv.pipeline.parse import parse as parse_stage
from networthcsv.pipeline.results import (
    CleanupAccountResult,
    ExtractStageResult,
    MetadataAccountResult,
    ParseAccountResult,
    PipelineResult,
)
from networthcsv.settings import ResolvedAccount, accounts_to_run

T = TypeVar("T")


def _report_account_banner(
    ctx: RunContext, account: ResolvedAccount, index: int, total: int
) -> None:
    ctx.reporter.account_banner(account, index=index, total=total)


def run_extract(ctx: RunContext) -> ExtractStageResult:
    return extract_stage.run_all(ctx)


def run_cleanup(ctx: RunContext) -> tuple[CleanupAccountResult, ...]:
    return _run_account_stage(ctx, cleanup_stage.run_account)


def run_metadata(ctx: RunContext) -> tuple[MetadataAccountResult, ...]:
    return _run_account_stage(ctx, metadata_stage.run_account)


def run_parse(ctx: RunContext) -> tuple[ParseAccountResult, ...]:
    return _run_account_stage(ctx, parse_stage.run_account)


def _run_account_stage(
    ctx: RunContext,
    run_account: Callable[[RunContext, ResolvedAccount], T],
) -> tuple[T, ...]:
    selected = accounts_to_run(ctx.settings)
    results: list[T] = []
    for index, account in enumerate(selected):
        if index > 0:
            ctx.reporter.blank_line()
        _report_account_banner(ctx, account, index, len(selected))
        results.append(run_account(ctx, account))
    return tuple(results)


def run_pipeline(ctx: RunContext) -> PipelineResult:
    extract_result = run_extract(ctx)
    ctx.reporter.blank_line()

    cleanup_results: list[CleanupAccountResult] = []
    metadata_results: list[MetadataAccountResult] = []
    parse_results: list[ParseAccountResult] = []
    selected = accounts_to_run(ctx.settings)

    for index, account in enumerate(selected):
        if index > 0:
            ctx.reporter.blank_line()
        _report_account_banner(ctx, account, index, len(selected))

        cleanup_result = cleanup_stage.run_account(ctx, account)
        cleanup_results.append(cleanup_result)
        ctx.reporter.blank_line()

        metadata_result = metadata_stage.run_account(ctx, account)
        metadata_results.append(metadata_result)
        ctx.reporter.blank_line()

        parse_result = parse_stage.run_account(ctx, account)
        parse_results.append(parse_result)

    return PipelineResult(
        extract=extract_result,
        cleanup=tuple(cleanup_results),
        metadata=tuple(metadata_results),
        parse=tuple(parse_results),
    )


def run_stage_for_accounts(
    ctx: RunContext,
    run_account: Callable[[RunContext, ResolvedAccount], object],
) -> None:
    """Run a per-account stage for all configured accounts."""
    _ = _run_account_stage(ctx, run_account)
