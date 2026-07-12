"""Public runtime API for embedding NetworthCSV in other applications."""

from __future__ import annotations

from typing import Literal

from networthcsv.cli import load_context
from networthcsv.context import RunContext
from networthcsv.errors import raise_if_cancelled
import networthcsv.pipeline.cleanup as cleanup_stage
import networthcsv.pipeline.metadata as metadata_stage
from networthcsv.pipeline.parse import parse as parse_stage
from networthcsv.pipeline.results import PipelineResult
from networthcsv.pipeline.runner import run_pipeline
from networthcsv.settings import ResolvedAccount

UploadSourceFormat = Literal["pdf", "csv", "zip"]

__all__ = [
    "load_context",
    "process",
    "process_upload",
]


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
    raise_if_cancelled(ctx)
    if source_format == "pdf":
        _ = cleanup_stage.run_account(
            ctx,
            account,
            upload_statement_date=statement_date,
        )
    elif source_format == "zip":
        _ = cleanup_stage.run_account(ctx, account)
    raise_if_cancelled(ctx)
    _ = metadata_stage.run_account(ctx, account)
    raise_if_cancelled(ctx)
    _ = parse_stage.run_account(ctx, account)
