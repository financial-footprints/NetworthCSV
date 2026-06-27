"""Public runtime API for embedding NetworthCSV in other applications."""

from __future__ import annotations

from networthcsv.cli import load_context
from networthcsv.context import RunContext
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

__all__ = [
    "cleanup",
    "extract",
    "load_context",
    "metadata",
    "parse",
    "process",
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
