"""Dispatch extract stage to Thunderbird or IMAP based on source.type."""

from __future__ import annotations

from src.context import RunContext
from src.pipeline.get_statements import imap as imap_pipeline
from src.pipeline.get_statements import thunderbird as thunderbird_pipeline
from src.settings import ResolvedAccount, ThunderbirdSource, accounts_to_run


def run_all(ctx: RunContext) -> None:
    source = ctx.settings.source
    if isinstance(source, ThunderbirdSource):
        for account in accounts_to_run(ctx.settings):
            thunderbird_pipeline.run_account(ctx, account)
            print()
    else:
        imap_pipeline.run_imap_extract(ctx)


def run_account(ctx: RunContext, account: ResolvedAccount) -> None:
    source = ctx.settings.source
    if isinstance(source, ThunderbirdSource):
        thunderbird_pipeline.run_account(ctx, account)
    else:
        raise SystemExit(
            "error: IMAP extract runs once for all accounts; use extract.run_all"
        )


def main() -> None:
    from src.cli import load_context

    ctx = load_context()
    run_all(ctx)
    ctx.alerts.flush()


if __name__ == "__main__":
    main()
