"""Pipeline orchestration for extract, cleanup, and parse stages."""

from __future__ import annotations

from collections.abc import Callable

from networthcsv.context import RunContext
from networthcsv.errors import raise_if_cancelled
import networthcsv.pipeline.cleanup as cleanup_stage
from networthcsv.pipeline.account_stage import (
    _report_account_banner,
    _run_account_stage,
)
from networthcsv.pipeline.get_statements import extract as extract_stage
import networthcsv.pipeline.metadata as metadata_stage
from networthcsv.pipeline.parse import parse as parse_stage
from networthcsv.pipeline.results import (
    CleanupAccountResult,
    ExtractStageResult,
    MetadataAccountResult,
    ParseAccountResult,
    PipelineResult,
)
from networthcsv.settings import ResolvedAccount


def run_extract(ctx: RunContext) -> ExtractStageResult:
    return extract_stage.run_all(ctx)


def run_cleanup(ctx: RunContext) -> tuple[CleanupAccountResult, ...]:
    return _run_account_stage(ctx, cleanup_stage.run_account)


def run_metadata(ctx: RunContext) -> tuple[MetadataAccountResult, ...]:
    return _run_account_stage(ctx, metadata_stage.run_account)


def run_parse(ctx: RunContext) -> tuple[ParseAccountResult, ...]:
    return _run_account_stage(ctx, parse_stage.run_account)


def run_pipeline(ctx: RunContext) -> PipelineResult:
    raise_if_cancelled(ctx)
    extract_result = run_extract(ctx)
    ctx.reporter.blank_line()

    cleanup_results: list[CleanupAccountResult] = []
    metadata_results: list[MetadataAccountResult] = []
    parse_results: list[ParseAccountResult] = []
    selected = ctx.settings.accounts_to_run()

    for index, account in enumerate(selected):
        raise_if_cancelled(ctx)
        if index > 0:
            ctx.reporter.blank_line()
        _report_account_banner(ctx, account, index, len(selected))

        cleanup_result = cleanup_stage.run_account(ctx, account)
        cleanup_results.append(cleanup_result)
        ctx.reporter.blank_line()

        raise_if_cancelled(ctx)
        metadata_result = metadata_stage.run_account(ctx, account)
        metadata_results.append(metadata_result)
        ctx.reporter.blank_line()

        raise_if_cancelled(ctx)
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
