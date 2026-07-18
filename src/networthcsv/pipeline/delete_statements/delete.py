"""Delete statement files produced by cleanup, metadata, and parse pipeline stages."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.results import DeleteAccountResult
from networthcsv.settings import ResolvedAccount, RunSettings
from networthcsv.utils.account import account_label
from networthcsv.utils.path import (
    account_download_path,
    account_metadata_path,
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    iter_transactions_csvs,
)

logger = logging.getLogger(__name__)


def collect_account_output_paths(
    download_path: Path,
    account: ResolvedAccount,
) -> tuple[Path, ...]:
    """Return cleanup, metadata, and parse output paths for an account."""
    files: dict[Path, None] = {}

    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        if pdf_path.is_file():
            files[pdf_path] = None
        if txt_path.is_file():
            files[txt_path] = None

    for csv_path in iter_statement_csvs(download_path, account):
        if csv_path.is_file():
            files[csv_path] = None

    for transactions_csv in iter_transactions_csvs(download_path, account):
        files[transactions_csv] = None

    metadata_path = account_metadata_path(download_path, account)
    if metadata_path.is_file():
        files[metadata_path] = None

    return tuple(sorted(files, key=lambda item: item.as_posix()))


def delete_account_statements(
    download_path: Path,
    account: ResolvedAccount,
) -> DeleteAccountResult:
    """Delete cleanup, metadata, and parse outputs for an account."""
    staging_dir = download_path / account.account_type / account.account_number
    metadata_path = account_metadata_path(download_path, account)
    files = collect_account_output_paths(download_path, account)

    files_removed = 0
    for path in files:
        path.unlink()
        logger.debug("removed: %s", path)
        files_removed += 1

    dirs_removed = 0
    for fy_dir in discover_account_fy_dirs(download_path, account):
        if fy_dir.is_dir() and not any(fy_dir.iterdir()):
            fy_dir.rmdir()
            logger.debug("removed (empty fy dir): %s", fy_dir)
            dirs_removed += 1

    return DeleteAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        files_removed=files_removed,
        dirs_removed=dirs_removed,
        metadata_path=metadata_path,
    )


def run_account(ctx: RunContext, account: ResolvedAccount) -> DeleteAccountResult:
    return delete_account_statements(ctx.settings.download_path, account)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete cleanup, metadata, and parse outputs for a configured account"
        ),
    )
    _ = parser.add_argument(
        "--identifier",
        "-i",
        dest="identifier",
        metavar="ID",
        required=True,
        help="Delete pipeline outputs for the account with this account_number",
    )
    _ = parser.add_argument(
        "--config",
        dest="config_path",
        metavar="PATH",
        help="Path to app.config.json (default: repo root or NETWORTHCSV_CONFIG)",
    )
    return parser


def main() -> None:
    from networthcsv.cli import cli_main, load_context
    from networthcsv.pipeline.reporter import ConsoleRunReporter

    def _run() -> None:
        parser = _build_parser()
        args = parser.parse_args()

        ctx = load_context(
            config_path=Path(args.config_path) if args.config_path else None,
            run_overrides=RunSettings(identifier=args.identifier),
            reporter=ConsoleRunReporter(),
        )

        selected = ctx.settings.accounts_to_run()
        if len(selected) != 1:
            raise SystemExit(
                f"error: expected exactly one account for identifier {args.identifier!r}"
            )

        account = selected[0]
        staging_dir = account_download_path(ctx.settings.download_path, account)
        print(f"delete pipeline outputs: {account_label(account)} {staging_dir}")
        print()

        result = run_account(ctx, account)

        print()
        print(
            f"done: {result.files_removed} file(s) removed, "
            f"{result.dirs_removed} dir(s) removed"
        )

    cli_main(_run)


if __name__ == "__main__":
    main()
