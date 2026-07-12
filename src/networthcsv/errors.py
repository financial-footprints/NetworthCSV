"""Library exceptions for NetworthCSV."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from networthcsv.context import RunContext


class NetworthCsvError(Exception):
    """Base error for NetworthCSV library callers."""


class ConfigError(NetworthCsvError):
    """Invalid or missing configuration."""


class StageError(NetworthCsvError):
    """Operational failure inside a pipeline stage."""


class JobCancelledError(NetworthCsvError):
    """Raised when a background job is cancelled cooperatively."""


def raise_if_cancelled(ctx: RunContext) -> None:
    if ctx.should_cancel is not None and ctx.should_cancel():
        raise JobCancelledError("cancelled by user")
