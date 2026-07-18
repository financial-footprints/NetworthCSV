"""Metadata stage entrypoint."""

from __future__ import annotations

import logging

from networthcsv.context import RunContext
from networthcsv.pipeline.metadata.persist import (
    read_account_metadata,
    refresh_account_metadata,
)
from networthcsv.pipeline.results import MetadataAccountResult
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.path import account_download_path

logger = logging.getLogger(__name__)


def run(
    account: ResolvedAccount,
    ctx: RunContext,
) -> MetadataAccountResult:
    staging_dir = account_download_path(ctx.settings.download_path, account)
    ctx.reporter.metadata_started(account.bank, staging_dir)

    output = refresh_account_metadata(ctx.settings.download_path, account)
    metadata = read_account_metadata(output)
    if metadata is None:
        raise RuntimeError(f"metadata missing after refresh: {output}")
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
