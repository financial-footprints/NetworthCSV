"""Metadata stage entrypoint."""

from __future__ import annotations

import logging
from dataclasses import replace

from networthcsv.context import RunContext
from networthcsv.pipeline.metadata.build import build_account_metadata
from networthcsv.pipeline.metadata.persist import (
    read_account_metadata,
    read_last_fetch_date,
    write_account_metadata,
)
from networthcsv.pipeline.results import MetadataAccountResult
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import format_account_date
from networthcsv.utils.path import account_download_path, account_metadata_path

logger = logging.getLogger(__name__)


def run(
    account: ResolvedAccount,
    ctx: RunContext,
) -> MetadataAccountResult:
    staging_dir = account_download_path(ctx.settings.download_path, account)
    ctx.reporter.metadata_started(account.bank, staging_dir)

    output = account_metadata_path(ctx.settings.download_path, account)
    existing = read_account_metadata(output)
    last_fetch_date = existing.last_fetch_date if existing is not None else None
    if last_fetch_date is None:
        last_fetch_date_value = read_last_fetch_date(ctx.settings.download_path, account)
        last_fetch_date = format_account_date(last_fetch_date_value)

    metadata = build_account_metadata(ctx.settings.download_path, account)
    if last_fetch_date is not None:
        metadata = replace(metadata, last_fetch_date=last_fetch_date)
    write_account_metadata(output, metadata)
    logger.debug("wrote metadata: %s", output)

    result = MetadataAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        output=output,
        statement_count=metadata.statement_count,
    )
    ctx.reporter.metadata_done(result)
    return result


def run_account(ctx: RunContext, account: ResolvedAccount) -> MetadataAccountResult:
    return run(account, ctx)


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(lambda: run_stage_main(run_account=run_account))


if __name__ == "__main__":
    main()
