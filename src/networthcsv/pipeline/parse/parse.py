"""Parse statement text/CSV files into per-period transactions-*.csv."""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.parse.statement import parse_statement_text
from networthcsv.pipeline.results import (
    ParseAccountResult,
    ParseFyResult,
    ParseStatementResult,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import parse_account_date
from networthcsv.utils.banks import get_handler
from networthcsv.utils.path import (
    account_download_path,
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    resolve_fy_limit,
    statement_period_from_path,
    transactions_csv_name,
)
from networthcsv.utils.statement_period import is_annual_period
from networthcsv.utils.transactions import Transaction

logger = logging.getLogger(__name__)

_CSV_COLUMNS = ("Date", "Description", "Ref", "Credited", "Debited", "File")


@dataclass(frozen=True)
class _StatementSource:
    source_path: Path
    source_name: str
    text: str
    statement_period: str
    period_stem: str
    is_annual: bool
    period_start: date | None
    period_end: date | None
    from_csv: bool


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


def _parse_csv_period_dates(
    csv_text: str,
    *,
    account: ResolvedAccount,
) -> tuple[date | None, date | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.resolve_csv_period_bounds(csv_text, account=account)


def _resolve_statement_period(path: Path) -> str:
    return statement_period_from_path(path) or path.stem


def _collect_statement_sources(
    download_path: Path,
    account: ResolvedAccount,
    *,
    fy_limit: Path | None = None,
) -> list[_StatementSource]:
    sources: list[_StatementSource] = []
    csv_periods: set[str] = set()

    for csv_path in iter_statement_csvs(download_path, account, fy_limit):
        statement_period = _resolve_statement_period(csv_path)
        text = csv_path.read_text(encoding="utf-8", errors="replace")
        period_start, period_end = _parse_csv_period_dates(text, account=account)
        csv_periods.add(csv_path.stem)
        sources.append(
            _StatementSource(
                source_path=csv_path,
                source_name=csv_path.name,
                text=text,
                statement_period=statement_period,
                period_stem=csv_path.stem,
                is_annual=is_annual_period(statement_period)
                or is_annual_period(csv_path.stem),
                period_start=period_start,
                period_end=period_end,
                from_csv=True,
            )
        )

    for pdf_path, txt_path in iter_statement_pairs(download_path, account, fy_limit):
        # CSV wins over TXT for the same period stem.
        if pdf_path.stem in csv_periods:
            logger.debug(
                "skipping txt %s; CSV present for period %s",
                txt_path.name,
                pdf_path.stem,
            )
            continue
        if not _should_parse_txt(pdf_path, txt_path):
            continue
        statement_period = _resolve_statement_period(pdf_path)
        text = txt_path.read_text(encoding="utf-8")
        period_start, period_end = _parse_period_dates(text, account=account)
        sources.append(
            _StatementSource(
                source_path=pdf_path,
                source_name=txt_path.name,
                text=text,
                statement_period=statement_period,
                period_stem=pdf_path.stem,
                is_annual=is_annual_period(statement_period)
                or is_annual_period(pdf_path.stem),
                period_start=period_start,
                period_end=period_end,
                from_csv=False,
            )
        )
    return sources


def _monthlies_within_annual(
    monthly: _StatementSource,
    annual: _StatementSource,
) -> bool:
    if monthly.period_start is None or monthly.period_end is None:
        return False
    if annual.period_start is None or annual.period_end is None:
        return False
    return (
        monthly.period_start >= annual.period_start
        and monthly.period_end <= annual.period_end
    )


def _select_sources(sources: list[_StatementSource]) -> list[_StatementSource]:
    annual_sources = [source for source in sources if source.is_annual]
    monthly_sources = [source for source in sources if not source.is_annual]
    selected_monthlies: list[_StatementSource] = []
    for monthly in monthly_sources:
        if any(_monthlies_within_annual(monthly, annual) for annual in annual_sources):
            logger.debug(
                "skipping monthly %s; covered by annual statement",
                monthly.statement_period,
            )
            continue
        selected_monthlies.append(monthly)
    return [*annual_sources, *selected_monthlies]


@dataclass(frozen=True)
class _ParsedSource:
    source: _StatementSource
    rows: list[Transaction]
    output: Path


def _parse_and_write_sources(
    selected_sources: list[_StatementSource],
    *,
    account: ResolvedAccount,
) -> list[_ParsedSource]:
    parsed: list[_ParsedSource] = []
    for source in selected_sources:
        rows = parse_statement_text(
            source.text,
            account=account,
            source_file=source.source_path.name,
        )
        output = source.source_path.parent / transactions_csv_name(source.period_stem)
        _write_csv(output, rows)
        parsed.append(_ParsedSource(source=source, rows=rows, output=output))
    return parsed


def _fy_name_for_source(source: _StatementSource) -> str:
    return source.source_path.parent.parent.parent.name


def process_fy_folder(
    account_fy_dir: Path,
    ctx: RunContext,
    *,
    parsed_by_fy: dict[str, list[_ParsedSource]],
) -> ParseFyResult:
    fy_name = account_fy_dir.parent.parent.name
    parsed = parsed_by_fy.get(fy_name, [])
    if not parsed:
        ctx.reporter.parse_fy_skipped(fy_name)
        return ParseFyResult(
            fy_name=fy_name,
            statements=(),
            transaction_count=0,
            outputs=(),
            skipped=True,
        )

    statements: list[ParseStatementResult] = []
    outputs: list[Path] = []
    total = 0
    for item in parsed:
        count = len(item.rows)
        total += count
        statements.append(
            ParseStatementResult(
                txt_name=item.source.source_name,
                transaction_count=count,
            )
        )
        outputs.append(item.output)
        ctx.reporter.parse_statement(item.source.source_name, count)

    result = ParseFyResult(
        fy_name=fy_name,
        statements=tuple(statements),
        transaction_count=total,
        outputs=tuple(outputs),
        skipped=False,
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
    parsed_sources = _parse_and_write_sources(selected_sources, account=account)

    parsed_by_fy: dict[str, list[_ParsedSource]] = defaultdict(list)
    for item in parsed_sources:
        parsed_by_fy[_fy_name_for_source(item.source)].append(item)

    total_txts = 0
    all_transactions = 0
    fy_results: list[ParseFyResult] = []

    for fy_dir in account_fy_dirs:
        fy_name = fy_dir.parent.parent.name
        ctx.reporter.parse_fy_started(fy_name)
        fy_result = process_fy_folder(
            fy_dir,
            ctx,
            parsed_by_fy=parsed_by_fy,
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
