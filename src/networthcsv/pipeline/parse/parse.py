"""Parse statement text files in FY folders into CSV files."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.results import (
    ParseAccountResult,
    ParseFyResult,
    ParseStatementResult,
)
from networthcsv.pipeline.parse.statement import parse_statement_text
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import parse_account_date
from networthcsv.utils.path import (
    account_download_path,
    discover_account_fy_dirs,
    fy_folder_name,
    iter_statement_pairs,
    resolve_fy_limit,
)
from networthcsv.utils.transactions import Transaction
from networthcsv.utils.statement_period import is_yearly_period

logger = logging.getLogger(__name__)

_CSV_COLUMNS = ("Date", "Description", "Ref", "Credited", "Debited", "File")


@dataclass(frozen=True)
class _StatementSource:
    pdf_path: Path
    txt_path: Path
    text: str
    statement_period: str
    is_yearly: bool
    period_start: date | None
    period_end: date | None


def _format_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _write_csv(path: Path, transactions: list[Transaction]) -> None:
    sorted_rows = sorted(
        transactions,
        key=lambda t: (t.date, t.source_file, t.ref_no or "", t.description),
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_CSV_COLUMNS)
        for txn in sorted_rows:
            writer.writerow(
                [
                    txn.date.isoformat(),
                    txn.description,
                    txn.ref_no or "",
                    _format_amount(txn.credited),
                    _format_amount(txn.debited),
                    txn.source_file,
                ]
            )


def _should_parse_txt(pdf_path: Path, txt_path: Path) -> bool:
    if not txt_path.is_file() or not pdf_path.is_file():
        logger.debug(
            "ignored %s: missing paired pdf or txt",
            pdf_path.name,
        )
        return False
    return True


def _parse_period_dates(
    text: str,
    *,
    account: ResolvedAccount,
) -> tuple[date | None, date | None]:
    from networthcsv.utils.banks.period import resolve_period_bounds

    period_start, period_end, _approximate = resolve_period_bounds(
        text,
        account=account,
    )
    start = parse_account_date(period_start, "period_start") if period_start else None
    end = parse_account_date(period_end, "period_end") if period_end else None
    return start, end


def _collect_statement_sources(
    download_path: Path,
    account: ResolvedAccount,
    *,
    fy_limit: Path | None = None,
) -> list[_StatementSource]:
    sources: list[_StatementSource] = []
    for pdf_path, txt_path in iter_statement_pairs(download_path, account, fy_limit):
        if not _should_parse_txt(pdf_path, txt_path):
            continue
        statement_period = pdf_path.stem
        text = txt_path.read_text(encoding="utf-8")
        period_start, period_end = _parse_period_dates(text, account=account)
        sources.append(
            _StatementSource(
                pdf_path=pdf_path,
                txt_path=txt_path,
                text=text,
                statement_period=statement_period,
                is_yearly=is_yearly_period(statement_period),
                period_start=period_start,
                period_end=period_end,
            )
        )
    return sources


def _monthlies_within_yearly(
    monthly: _StatementSource,
    yearly: _StatementSource,
) -> bool:
    if monthly.period_start is None or monthly.period_end is None:
        return False
    if yearly.period_start is None or yearly.period_end is None:
        return False
    return (
        monthly.period_start >= yearly.period_start
        and monthly.period_end <= yearly.period_end
    )


def _select_sources(sources: list[_StatementSource]) -> list[_StatementSource]:
    yearly_sources = [source for source in sources if source.is_yearly]
    monthly_sources = [source for source in sources if not source.is_yearly]
    selected_monthlies: list[_StatementSource] = []
    for monthly in monthly_sources:
        if any(_monthlies_within_yearly(monthly, yearly) for yearly in yearly_sources):
            logger.debug(
                "skipping monthly %s; covered by yearly statement",
                monthly.statement_period,
            )
            continue
        selected_monthlies.append(monthly)
    return [*yearly_sources, *selected_monthlies]


def _fy_name_for_transaction(txn_date: date) -> str:
    return fy_folder_name(txn_date.strftime("%Y-%m"))


def _parse_selected_sources(
    selected_sources: list[_StatementSource],
    *,
    account: ResolvedAccount,
    download_path: Path,
) -> tuple[dict[str, list[Transaction]], dict[str, list[ParseStatementResult]]]:
    transactions_by_fy: dict[str, list[Transaction]] = {}
    statements_by_fy: dict[str, list[ParseStatementResult]] = {}

    for source in selected_sources:
        rows = parse_statement_text(
            source.text,
            account=account,
            source_file=source.pdf_path.name,
        )
        if source.is_yearly:
            grouped: dict[str, list[Transaction]] = {}
            for txn in rows:
                fy_name = _fy_name_for_transaction(txn.date)
                grouped.setdefault(fy_name, []).append(txn)
            for fy_name, fy_rows in grouped.items():
                transactions_by_fy.setdefault(fy_name, []).extend(fy_rows)
                statements_by_fy.setdefault(fy_name, []).append(
                    ParseStatementResult(
                        txt_name=source.txt_path.name,
                        transaction_count=len(fy_rows),
                    )
                )
            continue

        fy_name = source.pdf_path.parent.parent.parent.name
        transactions_by_fy.setdefault(fy_name, []).extend(rows)
        statements_by_fy.setdefault(fy_name, []).append(
            ParseStatementResult(
                txt_name=source.txt_path.name,
                transaction_count=len(rows),
            )
        )

    return transactions_by_fy, statements_by_fy


def process_fy_folder(
    account_fy_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    transactions_by_fy: dict[str, list[Transaction]],
    statements_by_fy: dict[str, list[ParseStatementResult]],
) -> ParseFyResult:
    fy_name = account_fy_dir.parent.parent.name
    transactions = transactions_by_fy.get(fy_name, [])
    statements = statements_by_fy.get(fy_name, [])
    if not transactions and not statements:
        ctx.reporter.parse_fy_skipped(fy_name)
        return ParseFyResult(
            fy_name=fy_name,
            statements=(),
            transaction_count=0,
            output=None,
            skipped=True,
        )

    for statement in statements:
        ctx.reporter.parse_statement(statement.txt_name, statement.transaction_count)

    output = account_fy_dir / "transactions.csv"
    _write_csv(output, transactions)
    result = ParseFyResult(
        fy_name=fy_name,
        statements=tuple(statements),
        transaction_count=len(transactions),
        output=output,
    )
    ctx.reporter.parse_fy_done(result)
    return result


def run(
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    fy_limit: Path | None = None,
) -> ParseAccountResult:
    staging_dir = account_download_path(ctx.settings.download_path, account)
    account_fy_dirs = discover_account_fy_dirs(
        ctx.settings.download_path, account, fy_limit
    )
    if not account_fy_dirs:
        return ParseAccountResult(
            bank=account.bank,
            download_dir=staging_dir,
            fy_results=(),
            total_transactions=0,
            total_txts=0,
        )

    ctx.reporter.parse_started(account.bank, staging_dir)
    all_sources = _collect_statement_sources(
        ctx.settings.download_path, account, fy_limit=fy_limit
    )
    selected_sources = _select_sources(all_sources)
    transactions_by_fy, statements_by_fy = _parse_selected_sources(
        selected_sources,
        account=account,
        download_path=ctx.settings.download_path,
    )

    total_txts = 0
    all_transactions = 0
    fy_results: list[ParseFyResult] = []

    for account_fy_dir in account_fy_dirs:
        fy_name = account_fy_dir.parent.parent.name
        ctx.reporter.parse_fy_started(fy_name)
        fy_result = process_fy_folder(
            account_fy_dir,
            account,
            ctx,
            transactions_by_fy=transactions_by_fy,
            statements_by_fy=statements_by_fy,
        )
        fy_results.append(fy_result)
        total_txts += len(fy_result.statements)
        all_transactions += fy_result.transaction_count
        ctx.reporter.blank_line()

    result = ParseAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        fy_results=tuple(fy_results),
        total_transactions=all_transactions,
        total_txts=total_txts,
    )
    ctx.reporter.parse_account_done(result)
    return result


def run_account(ctx: RunContext, account: ResolvedAccount) -> ParseAccountResult:
    fy_limit = resolve_fy_limit(
        ctx.settings.download_path, account, ctx.settings.run.financial_year
    )
    return run(account, ctx, fy_limit=fy_limit)


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(lambda: run_stage_main(run_account=run_account))


if __name__ == "__main__":
    main()
