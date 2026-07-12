"""Build account metadata from canonical statement files on disk."""

from __future__ import annotations

from pathlib import Path

from networthcsv.pipeline.metadata.coverage import (
    build_period_covered,
    parse_account_date_value,
)
from networthcsv.pipeline.metadata.models import (
    AccountMetadata,
    StatementGranularity,
    StatementMetadata,
    YearlyStatementSummary,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import format_account_date
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.period import resolve_period_bounds
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    statement_csv_path,
    txt_path_for_pdf,
)
from networthcsv.utils.statement_period import (
    YearDisplay,
    covered_months_between,
    is_yearly_period,
    parse_month_period,
    year_key_for_period,
    year_key_label,
)


def statement_period_from_path(path: Path) -> str | None:
    period_id = path.stem
    if parse_month_period(period_id) is not None:
        return period_id
    if is_yearly_period(period_id):
        return period_id
    return None


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
    for account_fy_dir in discover_account_fy_dirs(download_path, account):
        if (account_fy_dir / "transactions.csv").is_file():
            return True
    return False


def extract_statement_balances(
    text: str,
    account: ResolvedAccount,
) -> tuple[str | None, str | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_opening_balance(text), handler.get_closing_balance(text)


def build_yearly_statement_summaries(
    statements: tuple[StatementMetadata, ...],
    *,
    year_display: YearDisplay,
) -> tuple[YearlyStatementSummary, ...]:
    summaries: list[YearlyStatementSummary] = []
    for statement in statements:
        if statement.granularity != "yearly":
            continue
        if (
            statement.year_key is None
            or statement.period_start is None
            or statement.period_end is None
        ):
            continue
        summaries.append(
            YearlyStatementSummary(
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


def build_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> AccountMetadata:
    statements_by_date: dict[str, tuple[Path | None, Path | None, Path | None]] = {}

    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        statement_date = statement_period_from_path(pdf_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (pdf_path, txt_path, existing[2])

    for csv_path in iter_statement_csvs(download_path, account):
        statement_date = statement_period_from_path(csv_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (existing[0], existing[1], csv_path)

    statements: list[StatementMetadata] = []
    account_formats: set[str] = set()

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
        else:
            opening_balance, closing_balance = None, None
            period_start, period_end, period_approximate = None, None, False

        granularity: StatementGranularity = (
            "yearly" if is_yearly_period(statement_date) else "monthly"
        )
        statement_covered_months: tuple[str, ...] = ()
        year_key: str | None = None
        if granularity == "yearly" and period_start and period_end:
            start_date = parse_account_date_value(period_start)
            end_date = parse_account_date_value(period_end)
            handler = get_handler(account.bank, account.variant)
            statement_covered_months = covered_months_between(start_date, end_date)
            year_key = year_key_for_period(
                start_date,
                end_date,
                year_display=handler.year_display(),
            )

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

    if has_transactions_csv(download_path, account):
        account_formats.add("csv")

    handler = get_handler(account.bank, account.variant)
    period_covered = build_period_covered(
        tuple(statements),
        tolerance=handler.balance_match_tolerance(),
    )

    return AccountMetadata(
        account_number=account.account_number,
        bank=account.bank,
        variant=account.variant,
        account_type=account.account_type,
        opening_date=format_account_date(account.opening_date),
        closing_date=format_account_date(account.closing_date),
        formats=tuple(sorted(account_formats)),
        statements=tuple(statements),
        statement_dates=statement_dates,
        starting=statement_dates[0] if statement_dates else None,
        ending=statement_dates[-1] if statement_dates else None,
        statement_count=len(statement_dates),
        period_covered=period_covered,
    )
