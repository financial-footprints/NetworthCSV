"""Dispatch extract stage to Thunderbird or IMAP based on source.type."""

from __future__ import annotations

from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.get_statements import imap as imap_pipeline
from networthcsv.pipeline.get_statements import thunderbird as thunderbird_pipeline
from networthcsv.pipeline.results import ExtractAccountResult, ExtractStageResult
from networthcsv.settings import ResolvedAccount, ThunderbirdSource, accounts_to_run


def run_all(ctx: RunContext) -> ExtractStageResult:
    source = ctx.settings.source
    if isinstance(source, ThunderbirdSource):
        results: list[ExtractAccountResult] = []
        accounts = accounts_to_run(ctx.settings)
        for index, account in enumerate(accounts):
            if index > 0:
                ctx.reporter.blank_line()
            ctx.reporter.account_banner(account, index=index, total=len(accounts))
            results.append(thunderbird_pipeline.run_account(ctx, account))
        return ExtractStageResult(accounts=tuple(results))
    return imap_pipeline.run_imap_extract(ctx)


def run_account(ctx: RunContext, account: ResolvedAccount) -> ExtractAccountResult:
    source = ctx.settings.source
    if isinstance(source, ThunderbirdSource):
        return thunderbird_pipeline.run_account(ctx, account)
    raise StageError(
        "IMAP extract runs once for all accounts; use extract.run_all or the runner"
    )


def main() -> None:
    from networthcsv.cli import cli_main, run_global_main
    from networthcsv.pipeline.runner import run_extract

    cli_main(lambda: run_global_main(run=run_extract))


if __name__ == "__main__":
    main()
