#!/usr/bin/env python3
"""Parse statement PDFs in FY folders into combined CSV files."""

from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

from src.bank import Transaction, get_parser
from src.bank.base import BankParser
from src.config import load_settings

_CSV_COLUMNS = ("Date", "Description", "Ref", "Credited", "Debited", "File")


def _discover_fy_folders(download_path: Path, limit: Path | None) -> list[Path]:
    if limit is not None:
        if not limit.is_dir():
            raise SystemExit(f"error: FY folder not found: {limit}")
        return [limit]
    folders = sorted(p for p in download_path.glob("FY*") if p.is_dir())
    if not folders:
        print(f"warning: no FY folders found under {download_path}", file=sys.stderr)
    return folders


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


def process_fy_folder(
    fy_dir: Path,
    parser: BankParser,
    password: str | None,
) -> tuple[int, list[Transaction]]:
    pdfs = sorted(fy_dir.glob("*.pdf"))
    if not pdfs:
        print(f"skip (no pdfs): {fy_dir}")
        return 0, []

    transactions: list[Transaction] = []
    for pdf_path in pdfs:
        rows = parser.parse_pdf(pdf_path, password)
        transactions.extend(rows)
        print(f"  {pdf_path.name}: {len(rows)} transaction(s)")

    output = fy_dir / "transactions.csv"
    _write_csv(output, transactions)
    print(f"wrote: {output} ({len(transactions)} transaction(s) from {len(pdfs)} pdf(s))")
    return len(pdfs), transactions


def main() -> None:
    settings = load_settings()
    parser = get_parser(settings.bank)
    password = settings.pdf_password

    limit: Path | None = None
    if len(sys.argv) > 1:
        limit = Path(sys.argv[1]).expanduser()
        if not limit.is_absolute():
            limit = (settings.download_path / limit).resolve()

    if not settings.download_path.is_dir():
        print(f"error: download directory not found: {settings.download_path}", file=sys.stderr)
        sys.exit(1)

    fy_folders = _discover_fy_folders(settings.download_path, limit)
    if not fy_folders:
        sys.exit(0)

    print(f"parse: bank={settings.bank}, download_path={settings.download_path}")
    print()

    total_pdfs = 0
    all_transactions: list[Transaction] = []

    for fy_dir in fy_folders:
        print(f"folder: {fy_dir.name}")
        pdf_count, transactions = process_fy_folder(fy_dir, parser, password)
        total_pdfs += pdf_count
        all_transactions.extend(transactions)
        print()

    if settings.create_combined_csv and limit is None:
        combined_path = settings.download_path / "combined_transactions.csv"
        _write_csv(combined_path, all_transactions)
        print(f"wrote combined: {combined_path} ({len(all_transactions)} transaction(s))")
        print()

    print(f"done: {len(all_transactions)} transaction(s) from {total_pdfs} pdf(s) in {len(fy_folders)} folder(s)")


if __name__ == "__main__":
    main()
