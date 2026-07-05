"""Parse statement text files in FY folders into CSV files."""

from __future__ import annotations

import csv
import logging
from decimal import Decimal
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.results import (
    ParseAccountResult,
    ParseFyResult,
    ParseStatementResult,
)
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_pdfs,
    resolve_fy_limit,
    txt_path_for_pdf,
)
from networthcsv.utils.transactions import Transaction
from networthcsv.pipeline.parse.statement import parse_statement_text
from networthcsv.settings import ResolvedAccount, account_download_path

logger = logging.getLogger(__name__)

_CSV_COLUMNS = ("Date", "Description", "Ref", "Credited", "Debited", "File")


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


def process_fy_folder(
    account_fy_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
) -> ParseFyResult:
    fy_name = account_fy_dir.parent.parent.name
    pdfs = list(iter_pdfs(account_fy_dir))
    if not pdfs:
        ctx.reporter.parse_fy_skipped(fy_name)
        return ParseFyResult(
            fy_name=fy_name,
            statements=(),
            transaction_count=0,
            output=None,
            skipped=True,
        )

    transactions: list[Transaction] = []
    statements: list[ParseStatementResult] = []
    for pdf_path in pdfs:
        txt_path = txt_path_for_pdf(pdf_path)
        if not _should_parse_txt(pdf_path, txt_path):
            continue
        text = txt_path.read_text(encoding="utf-8")
        rows = parse_statement_text(text, account=account, source_file=pdf_path.name)
        transactions.extend(rows)
        statements.append(
            ParseStatementResult(
                txt_name=txt_path.name,
                transaction_count=len(rows),
            )
        )
        ctx.reporter.parse_statement(txt_path.name, len(rows))

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
    staging_dir = account_download_path(ctx.settings, account)
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

    total_txts = 0
    all_transactions = 0
    fy_results: list[ParseFyResult] = []

    for account_fy_dir in account_fy_dirs:
        fy_name = account_fy_dir.parent.parent.name
        ctx.reporter.parse_fy_started(fy_name)
        fy_result = process_fy_folder(account_fy_dir, account, ctx)
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
