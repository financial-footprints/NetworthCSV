"""Build account metadata from canonical statement files on disk."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.pipeline.metadata.coverage import build_period_covered
from networthcsv.pipeline.metadata.models import (
    AccountMetadata,
    StatementGranularity,
    StatementMetadata,
    AnnualStatementSummary,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import (
    format_account_date,
    require_account_date_str,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.period import resolve_period_bounds
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    iter_transactions_csvs,
    statement_csv_path,
    statement_period_from_path,
    txt_path_for_pdf,
)
from networthcsv.utils.statement_period import (
    YearDisplay,
    covered_months_between,
    is_annual_period,
    is_calendar_year_period,
    period_for_year_key,
    year_key_label,
)

logger = logging.getLogger(__name__)


def statement_formats(
    pdf_path: Path | None,
    txt_path: Path | None,
    csv_path: Path | None,
) -> tuple[str, ...]:
    formats: list[str] = []
    if pdf_path is not None and pdf_path.is_file():
        formats.append("pdf")
    if txt_path is not None and txt_path.is_file():
        formats.append("txt")
    if csv_path is not None and csv_path.is_file():
        formats.append("csv")
    return tuple(formats)


def has_transactions_csv(download_path: Path, account: ResolvedAccount) -> bool:
    for _path in iter_transactions_csvs(download_path, account):
        return True
    return False


def extract_statement_balances(
    text: str,
    account: ResolvedAccount,
) -> tuple[str | None, str | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_opening_balance(text), handler.get_closing_balance(text)


def build_annual_statement_summaries(
    statements: tuple[StatementMetadata, ...],
    *,
    year_display: YearDisplay,
) -> tuple[AnnualStatementSummary, ...]:
    summaries: list[AnnualStatementSummary] = []
    seen_year_keys: dict[str, str] = {}
    for statement in statements:
        if statement.granularity != "annual":
            continue
        if (
            statement.year_key is None
            or statement.period_start is None
            or statement.period_end is None
        ):
            logger.warning(
                "annual statement %s excluded from annual_statements: "
                "missing year_key or period bounds (period_start=%s, period_end=%s); "
                "Annual CSV chip will not appear in calendar",
                statement.statement_date,
                statement.period_start,
                statement.period_end,
            )
            continue
        prior = seen_year_keys.get(statement.year_key)
        if prior is not None:
            logger.warning(
                "annual statement %s shares year_key %s with %s; "
                "calendar UI keeps one entry per year_key (last wins in API map)",
                statement.statement_date,
                statement.year_key,
                prior,
            )
        seen_year_keys[statement.year_key] = statement.statement_date
        summaries.append(
            AnnualStatementSummary(
                year_key=statement.year_key,
                statement_date=statement.statement_date,
                label=year_key_label(
                    statement.year_key,
                    year_display=year_display,
                ),
                period_start=statement.period_start,
                period_end=statement.period_end,
                formats=statement.formats,
            )
        )
    return tuple(summaries)


def _count_annual_csvs_on_disk(download_path: Path, account: ResolvedAccount) -> int:
    count = 0
    for csv_path in iter_statement_csvs(download_path, account):
        if is_calendar_year_period(csv_path.stem) or is_annual_period(
            statement_period_from_path(csv_path) or ""
        ):
            count += 1
    return count


def _log_annual_metadata_summary(
    download_path: Path,
    account: ResolvedAccount,
    statements: tuple[StatementMetadata, ...],
    *,
    year_display: YearDisplay,
) -> None:
    annual_csv_on_disk = _count_annual_csvs_on_disk(download_path, account)
    summaries = build_annual_statement_summaries(
        statements,
        year_display=year_display,
    )
    annual_with_csv = sum(1 for item in summaries if "csv" in item.formats)
    if annual_csv_on_disk != annual_with_csv:
        logger.warning(
            "annual CSV visibility: %d annual CSV file(s) on disk → "
            "%d annual_statements with csv format "
            "(re-run metadata after fixing period bounds or year_key collisions)",
            annual_csv_on_disk,
            annual_with_csv,
        )
    elif annual_csv_on_disk:
        logger.info(
            "annual CSV visibility: %d annual CSV file(s) → "
            "%d calendar Annual CSV chip(s)",
            annual_csv_on_disk,
            annual_with_csv,
        )


def build_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> AccountMetadata:
    statements_by_date: dict[str, tuple[Path | None, Path | None, Path | None]] = {}
    folders = discover_account_fy_dirs(download_path, account)

    for pdf_path, txt_path in iter_statement_pairs(
        download_path, account, folders=folders
    ):
        statement_date = statement_period_from_path(pdf_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (pdf_path, txt_path, existing[2])

    for csv_path in iter_statement_csvs(download_path, account, folders=folders):
        statement_date = statement_period_from_path(csv_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (existing[0], existing[1], csv_path)

    statements: list[StatementMetadata] = []
    account_formats: set[str] = set()
    handler = get_handler(account.bank, account.variant)
    year_display = handler.year_display()

    for statement_date in sorted(statements_by_date):
        pdf_path, txt_path, csv_path = statements_by_date[statement_date]
        if txt_path is None and pdf_path is not None:
            txt_path = txt_path_for_pdf(pdf_path)
        if csv_path is None:
            csv_path = statement_csv_path(download_path, account, statement_date)
        formats = statement_formats(pdf_path, txt_path, csv_path)
        if not formats:
            continue
        account_formats.update(formats)
        if txt_path is not None and txt_path.is_file():
            text = txt_path.read_text(encoding="utf-8")
            opening_balance, closing_balance = extract_statement_balances(
                text,
                account,
            )
            period_start, period_end, period_approximate = resolve_period_bounds(
                text,
                account=account,
            )
        elif csv_path is not None and csv_path.is_file():
            opening_balance, closing_balance = None, None
            csv_text = csv_path.read_text(encoding="utf-8", errors="replace")
            csv_start, csv_end = handler.resolve_csv_period_bounds(
                csv_text, account=account
            )
            if csv_start is not None and csv_end is not None:
                period_start = require_account_date_str(csv_start)
                period_end = require_account_date_str(csv_end)
                period_approximate = False
            else:
                period_start, period_end, period_approximate = None, None, False
                if is_annual_period(statement_date):
                    logger.warning(
                        "annual CSV %s: could not resolve period bounds "
                        "(check opening_date and transaction rows); "
                        "Annual CSV chip may not appear in calendar",
                        csv_path.name,
                    )
        else:
            opening_balance, closing_balance = None, None
            period_start, period_end, period_approximate = None, None, False

        granularity: StatementGranularity = (
            "annual" if is_annual_period(statement_date) else "monthly"
        )
        statement_covered_months: tuple[str, ...] = ()
        year_key: str | None = None
        if granularity == "annual":
            year_key = statement_date
            fy_start, fy_end = period_for_year_key(
                statement_date,
                year_display=year_display,
            )
            period_start = require_account_date_str(fy_start)
            period_end = require_account_date_str(fy_end)
            period_approximate = False
            statement_covered_months = covered_months_between(fy_start, fy_end)

        statements.append(
            StatementMetadata(
                statement_date=statement_date,
                formats=formats,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                period_start=period_start,
                period_end=period_end,
                period_approximate=period_approximate,
                granularity=granularity,
                covered_months=statement_covered_months,
                year_key=year_key,
            )
        )

    statement_dates = tuple(item.statement_date for item in statements)
    statements_tuple = tuple(statements)

    if has_transactions_csv(download_path, account):
        account_formats.add("csv")

    period_covered = build_period_covered(
        statements_tuple,
        tolerance=handler.balance_match_tolerance(),
    )

    _log_annual_metadata_summary(
        download_path,
        account,
        statements_tuple,
        year_display=year_display,
    )

    return AccountMetadata(
        account_number=account.account_number,
        bank=account.bank,
        variant=account.variant,
        account_type=account.account_type,
        opening_date=format_account_date(account.opening_date),
        closing_date=format_account_date(account.closing_date),
        formats=tuple(sorted(account_formats)),
        statements=statements_tuple,
        statement_dates=statement_dates,
        starting=statement_dates[0] if statement_dates else None,
        ending=statement_dates[-1] if statement_dates else None,
        statement_count=len(statement_dates),
        period_covered=period_covered,
    )
