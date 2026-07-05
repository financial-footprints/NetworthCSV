"""Public runtime API for embedding NetworthCSV in other applications."""

from __future__ import annotations

from typing import Literal

from networthcsv.cli import load_context
from networthcsv.context import RunContext
from networthcsv.pipeline.cleanup import cleanup as cleanup_stage
from networthcsv.pipeline.metadata import metadata as metadata_stage
from networthcsv.pipeline.parse import parse as parse_stage
from networthcsv.pipeline.results import (
    CleanupAccountResult,
    ExtractStageResult,
    MetadataAccountResult,
    ParseAccountResult,
    PipelineResult,
)
from networthcsv.pipeline.runner import (
    run_cleanup,
    run_extract,
    run_metadata,
    run_parse,
    run_pipeline,
)
from networthcsv.settings import ResolvedAccount

UploadSourceFormat = Literal["pdf", "csv"]

__all__ = [
    "cleanup",
    "extract",
    "load_context",
    "metadata",
    "parse",
    "process",
    "process_upload",
]


def extract(ctx: RunContext) -> ExtractStageResult:
    return run_extract(ctx)


def cleanup(ctx: RunContext) -> tuple[CleanupAccountResult, ...]:
    return run_cleanup(ctx)


def metadata(ctx: RunContext) -> tuple[MetadataAccountResult, ...]:
    return run_metadata(ctx)


def parse(ctx: RunContext) -> tuple[ParseAccountResult, ...]:
    return run_parse(ctx)


def process(ctx: RunContext) -> PipelineResult:
    return run_pipeline(ctx)


def process_upload(
    ctx: RunContext,
    account: ResolvedAccount,
    *,
    source_format: UploadSourceFormat,
    statement_date: str | None = None,
) -> None:
    """Run post-upload stages for one account without re-fetching email."""
    if source_format == "pdf":
        _ = cleanup_stage.run_account(
            ctx,
            account,
            upload_statement_date=statement_date,
        )
    _ = metadata_stage.run_account(ctx, account)
    _ = parse_stage.run_account(ctx, account)
