#!/usr/bin/env python3
"""Parse statement text files in txt/FY folders into CSV files."""

from __future__ import annotations

import argparse
import csv
import logging
from decimal import Decimal
from pathlib import Path

from src.cli import add_config_argument
from src.core.accounts import iter_accounts
from src.core.paths import discover_fy_folders, txt_is_current, txt_path_for_pdf
from src.logging_config import configure_logging
from src.parsers import Transaction, get_parser
from src.parsers.base import BankParser
from src.settings import AccountSettings, Settings, load_settings, parser_bank, resolve_config_path

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
    if not txt_path.is_file():
        logger.info("skip (no txt): %s", txt_path.name)
        return False
    if not pdf_path.is_file():
        logger.warning("source PDF missing for %s, skipping", txt_path.name)
        return False
    if not txt_is_current(pdf_path, txt_path):
        logger.warning("txt stale for %s, re-run text_extract", txt_path.name)
    return True


def process_fy_folder(
    download_dir: Path,
    fy_dir: Path,
    parser: BankParser,
) -> tuple[int, list[Transaction]]:
    pdfs = sorted(fy_dir.glob("*.pdf"))
    if not pdfs:
        print(f"skip (no pdfs): {fy_dir}")
        return 0, []

    transactions: list[Transaction] = []
    parsed_count = 0
    for pdf_path in pdfs:
        txt_path = txt_path_for_pdf(download_dir, fy_dir, pdf_path)
        if not _should_parse_txt(pdf_path, txt_path):
            continue
        text = txt_path.read_text(encoding="utf-8")
        rows = parser.parse_text(text, source_file=pdf_path.name)
        transactions.extend(rows)
        parsed_count += 1
        print(f"  {txt_path.name}: {len(rows)} transaction(s)")

    output = fy_dir / "transactions.csv"
    _write_csv(output, transactions)
    print(f"wrote: {output} ({len(transactions)} transaction(s) from {parsed_count} txt(s))")
    return parsed_count, transactions


def run(
    download_dir: Path,
    bank: str,
    create_combined_csv: bool,
    fy_limit: Path | None = None,
) -> None:
    if not download_dir.is_dir():
        raise SystemExit(f"error: download directory not found: {download_dir}")

    parser = get_parser(bank)
    fy_folders = discover_fy_folders(download_dir, fy_limit)
    if not fy_folders:
        return

    print(f"parse: bank={bank}, download_path={download_dir}")
    print()

    total_txts = 0
    all_transactions: list[Transaction] = []

    for fy_dir in fy_folders:
        print(f"folder: {fy_dir.name}")
        txt_count, transactions = process_fy_folder(download_dir, fy_dir, parser)
        total_txts += txt_count
        all_transactions.extend(transactions)
        print()

    if create_combined_csv and fy_limit is None:
        combined_path = download_dir / "combined_transactions.csv"
        _write_csv(combined_path, all_transactions)
        print(f"wrote combined: {combined_path} ({len(all_transactions)} transaction(s))")
        print()

    print(
        f"done: {len(all_transactions)} transaction(s) from {total_txts} txt(s) in {len(fy_folders)} folder(s)"
    )


def _resolve_fy_limit(download_dir: Path, fy_name: str | None) -> Path | None:
    if fy_name is None:
        return None
    limit = Path(fy_name).expanduser()
    if not limit.is_absolute():
        limit = (download_dir / limit).resolve()
    return limit


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Parse statement text files into CSV files.")
    add_config_argument(parser)
    parser.add_argument(
        "--account",
        type=Path,
        default=None,
        metavar="DIR",
        help="Single account directory (must match a configured {download_path}/{bank}/ path)",
    )
    parser.add_argument(
        "--fy",
        default=None,
        metavar="NAME",
        help="Optional FY folder name (e.g. FY23-2024) within each account directory",
    )
    args = parser.parse_args()
    settings = load_settings(resolve_config_path(args.config))

    def run_account(download_dir: Path, account: AccountSettings, settings: Settings) -> None:
        fy_limit = _resolve_fy_limit(download_dir, args.fy)
        run(download_dir, parser_bank(account), settings.create_combined_csv, fy_limit)

    iter_accounts(settings, run_account, download_dir=args.account)


if __name__ == "__main__":
    main()
