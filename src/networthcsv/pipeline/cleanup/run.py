"""Cleanup stage entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.cleanup.canonical import remove_ineligible_canonical_outputs
from networthcsv.pipeline.cleanup.exclusion import statement_should_exclude
from networthcsv.pipeline.cleanup.grouping import collect_staging_groups
from networthcsv.pipeline.cleanup.orphans import sweep_orphans
from networthcsv.pipeline.cleanup.prepare_csv_month import prepare_csv_month
from networthcsv.pipeline.cleanup.prepare_month import prepare_month
from networthcsv.pipeline.cleanup import staging
from networthcsv.pipeline.results import CleanupAccountResult
from networthcsv.pipeline.upload import manual_upload_pdf_path
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.text import statement_text_eligible
from networthcsv.utils.path import (
    account_download_path,
    statement_csv_path,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
)

logger = logging.getLogger(__name__)


def run(
    staging_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    upload_statement_date: str | None = None,
) -> CleanupAccountResult:
    if not staging_dir.is_dir():
        ctx.reporter.cleanup_skipped(account.bank, staging_dir)
        return CleanupAccountResult(
            bank=account.bank,
            download_dir=staging_dir,
            unsupported_staging_removed=0,
            decrypted=0,
            prepared=0,
            rejected=0,
            orphans_removed=0,
            skipped=True,
        )

    download_path = ctx.settings.download_path
    ctx.reporter.cleanup_started(account.bank, staging_dir)

    alerts = ctx.alerts
    removed = staging.prune_unsupported_staging_files(staging_dir)
    decrypted = staging.decrypt_pdfs_in_place(staging_dir, account.passwords)

    prepared = 0
    rejected = 0
    pdf_paths: list[Path] | None
    csv_paths: list[Path] | None
    if upload_statement_date is not None:
        upload_path = manual_upload_pdf_path(staging_dir, upload_statement_date)
        pdf_paths = [upload_path] if upload_path.is_file() else []
        csv_paths = []
    else:
        pdf_paths = None
        csv_paths = None
    collected, csv_collected = collect_staging_groups(
        staging_dir,
        account,
        pdf_paths=pdf_paths,
        csv_paths=csv_paths,
    )
    _ = staging.prune_excluded_staging(
        staging_dir, account, collected, csv_collected=csv_collected
    )
    _ = remove_ineligible_canonical_outputs(download_path, account)

    for month, candidates in sorted(collected.groups.items()):
        if month == "unknown-month":
            logger.debug(
                "skip unknown-month: leaving %d file(s) in %s",
                len(candidates),
                staging_dir,
            )
            continue

        pdf_out = statement_pdf_path(download_path, account, month)
        txt_out = txt_path_for_pdf(pdf_out)
        canonical = pdf_out if pdf_out.is_file() else None
        extra = [
            path
            for path in candidates
            if path.is_file()
            and (canonical is None or path.resolve() != canonical.resolve())
        ]
        if not extra:
            if (
                pdf_out.is_file()
                and txt_out.is_file()
                and txt_is_current(pdf_out, txt_out)
            ):
                txt_content = txt_out.read_text(encoding="utf-8")
                if statement_should_exclude(
                    txt_content,
                    txt_content,
                    account=account,
                    is_manual=False,
                ):
                    _ = pdf_out.unlink()
                    _ = txt_out.unlink()
                    logger.debug(
                        "removed (excluded statement): canonical outputs for %s",
                        month,
                    )
                    continue
                if statement_text_eligible(
                    txt_content,
                    text_contains=account.statement.text_contains,
                    text_not_contains=account.statement.text_not_contains,
                    is_manual=False,
                ):
                    continue
                _ = pdf_out.unlink()
                _ = txt_out.unlink()
                logger.debug(
                    "removed (text_not_contains): canonical outputs for %s",
                    month,
                )

        month_prepared, month_rejected = prepare_month(
            staging_dir,
            download_path,
            month,
            candidates,
            account,
            raw_by_path=collected.raw_by_path,
            path_month=collected.path_month,
            path_hash=collected.path_hash,
            path_period_source=collected.path_period_source,
            alerts=alerts,
        )
        prepared += month_prepared
        rejected += month_rejected

    # CSV path: skip when this run is a targeted PDF upload.
    if upload_statement_date is None:
        for month, candidates in sorted(csv_collected.groups.items()):
            if month == "unknown-month":
                names = ", ".join(path.name for path in candidates)
                logger.warning(
                    "skip unknown-month csv: leaving %d file(s) in %s (%s); "
                    "check opening_date and period inference",
                    len(candidates),
                    staging_dir,
                    names,
                )
                continue
            csv_out = statement_csv_path(download_path, account, month)
            extra = [
                path
                for path in candidates
                if path.is_file()
                and (not csv_out.is_file() or path.resolve() != csv_out.resolve())
            ]
            if not extra and csv_out.is_file():
                continue
            month_prepared, month_rejected = prepare_csv_month(
                staging_dir,
                download_path,
                month,
                candidates,
                account,
                raw_by_path=csv_collected.raw_by_path,
                path_month=csv_collected.path_month,
                path_hash=csv_collected.path_hash,
                path_period_source=csv_collected.path_period_source,
                alerts=alerts,
            )
            prepared += month_prepared
            rejected += month_rejected

    orphans = sweep_orphans(ctx.settings, account)

    result = CleanupAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        unsupported_staging_removed=removed,
        decrypted=decrypted,
        prepared=prepared,
        rejected=rejected,
        orphans_removed=orphans,
    )
    ctx.reporter.cleanup_done(result)
    return result


def run_account(
    ctx: RunContext,
    account: ResolvedAccount,
    *,
    upload_statement_date: str | None = None,
) -> CleanupAccountResult:
    return run(
        account_download_path(ctx.settings.download_path, account),
        account,
        ctx,
        upload_statement_date=upload_statement_date,
    )


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(lambda: run_stage_main(run_account=run_account))


if __name__ == "__main__":
    main()
