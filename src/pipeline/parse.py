#!/usr/bin/env python3
"""Parse statement text files in FY folders into CSV files."""

from __future__ import annotations

import csv
import logging
from decimal import Decimal
from pathlib import Path

from src.context import RunContext
from src.core.paths import (
    discover_fy_folders,
    pdfs_in_fy,
    resolve_fy_limit,
    txt_path_for_pdf,
)
from src.core.transactions import Transaction
from src.parsers.statement import parse_statement_text
from src.settings import ResolvedAccount

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
    download_dir: Path,
    fy_dir: Path,
) -> tuple[int, list[Transaction]]:
    pdfs = pdfs_in_fy(download_dir, fy_dir)
    if not pdfs:
        print(f"skip (no pdfs): {fy_dir}")
        return 0, []

    transactions: list[Transaction] = []
    parsed_count = 0
    for pdf_path in pdfs:
        txt_path = txt_path_for_pdf(download_dir, pdf_path)
        if not _should_parse_txt(pdf_path, txt_path):
            continue
        text = txt_path.read_text(encoding="utf-8")
        rows = parse_statement_text(text, source_file=pdf_path.name)
        transactions.extend(rows)
        parsed_count += 1
        print(f"  {txt_path.name}: {len(rows)} transaction(s)")

    output = fy_dir / "transactions.csv"
    _write_csv(output, transactions)
    print(f"wrote: {output} ({len(transactions)} transaction(s) from {parsed_count} txt(s))")
    return parsed_count, transactions


def run(
    download_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    fy_limit: Path | None = None,
) -> None:
    if not download_dir.is_dir():
        raise SystemExit(f"error: download directory not found: {download_dir}")

    fy_folders = discover_fy_folders(download_dir, fy_limit)
    if not fy_folders:
        return

    print(f"parse: {account.bank} {download_dir}")
    print()

    total_txts = 0
    all_transactions: list[Transaction] = []

    for fy_dir in fy_folders:
        print(f"folder: {fy_dir.name}")
        txt_count, transactions = process_fy_folder(download_dir, fy_dir)
        total_txts += txt_count
        all_transactions.extend(transactions)
        print()

    if ctx.settings.run.create_combined_csv and fy_limit is None:
        combined_path = download_dir / "combined_transactions.csv"
        _write_csv(combined_path, all_transactions)
        print(f"wrote combined: {combined_path} ({len(all_transactions)} transaction(s))")
        print()

    print(
        f"done: {len(all_transactions)} transaction(s) from {total_txts} txt(s) in {len(fy_folders)} folder(s)"
    )


def main() -> None:
    from src.cli import run_stage_main

    def run_account(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
        fy_limit = resolve_fy_limit(download_dir, ctx.settings.run.fy)
        run(download_dir, account, ctx, fy_limit=fy_limit)

    run_stage_main(run_account=run_account)


if __name__ == "__main__":
    main()
