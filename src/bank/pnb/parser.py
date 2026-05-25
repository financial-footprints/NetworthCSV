"""Parse transaction rows from PNB credit card statement PDFs."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from src.bank.base import Transaction

# Transaction rows: DD-MMM-YYYY  DD-MMM-YYYY  <description>  <amount> [Cr]
_TXN_ROW = re.compile(
    r"(\d{2}-[A-Za-z]{3}-\d{4})\s+\d{2}-[A-Za-z]{3}-\d{4}\s+(.+?)\s+([\d,]+\.\d{2})(\s+Cr)?\s*$",
    re.IGNORECASE,
)

# Marks the start of the transaction table
_SECTION_HEADERS = ("Transaction Date", "Trnx Details")

# Marks the end of the transaction table
_FOOTER_MARKERS = ("Total Purchase", "End of Statement", "Total Taxable Value")


def _open_reader(path: Path, password: str | None) -> PdfReader:
    reader = PdfReader(str(path))
    if not reader.is_encrypted:
        return reader
    if not password:
        raise SystemExit(f"error: encrypted PDF requires password: {path}")
    if reader.decrypt(password) == 0:
        raise SystemExit(f"error: wrong pdf password for {path}")
    return reader


def _extract_pages(path: Path, password: str | None) -> list[str]:
    reader = _open_reader(path, password)
    result: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            result.append(text)
    return result


def _find_section_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (start_idx, end_idx) of the transaction table lines."""
    start = None
    # Track how many header keywords we've seen; section starts once any is found.
    for i, line in enumerate(lines):
        if start is None and any(kw in line for kw in _SECTION_HEADERS):
            start = i + 1
            continue
        if start is not None and any(marker in line for marker in _FOOTER_MARKERS):
            return start, i

    # If no footer found, return to end of list
    if start is not None:
        return start, len(lines)
    # Header never found — fall back to scanning everything
    return 0, len(lines)


def _parse_date(raw: str) -> datetime:
    """Parse DD-MMM-YYYY in either upper or title case."""
    # strptime %b is locale-dependent; normalise to title case to be safe
    normalised = raw[:3] + raw[3:6].title() + raw[6:]
    return datetime.strptime(normalised, "%d-%b-%Y")


def _parse_amount(raw: str, is_credit: bool) -> tuple[Decimal, Decimal]:
    amount = Decimal(raw.replace(",", ""))
    if is_credit:
        return amount, Decimal(0)
    return Decimal(0), amount


def _try_match_row(line: str, source_file: str) -> Transaction | None:
    m = _TXN_ROW.search(line)
    if not m:
        return None
    date_raw, description, amount_raw, credit_suffix = m.groups()
    try:
        txn_date = _parse_date(date_raw).date()
    except ValueError:
        return None
    credited, debited = _parse_amount(amount_raw, credit_suffix is not None)
    return Transaction(
        date=txn_date,
        description=description.strip(),
        credited=credited,
        debited=debited,
        source_file=source_file,
    )


def _extract_from_text(text: str, source_file: str) -> list[Transaction]:
    """Parse transactions from a block of extracted text."""
    lines = [line.strip() for line in text.splitlines()]
    start, end = _find_section_bounds(lines)
    section_lines = lines[start:end]

    transactions: list[Transaction] = []
    for line in section_lines:
        if not line:
            continue
        txn = _try_match_row(line, source_file)
        if txn is not None:
            transactions.append(txn)

    return transactions


def parse_pdf(path: Path, password: str | None) -> list[Transaction]:
    """Extract all transactions from a PNB credit card PDF statement."""
    pages = _extract_pages(path, password)
    if not pages:
        print(f"  warning: no text extracted from {path.name}")
        return []

    transactions: list[Transaction] = []

    # Process each page independently so the section detection works per-page.
    # PNB statements put the transaction table on page 1; multi-month PDFs may
    # repeat the header on subsequent pages.
    for page_text in pages:
        transactions.extend(_extract_from_text(page_text, path.name))

    # Deduplicate identical rows that might appear if the header repeats
    seen: set[Transaction] = set()
    unique: list[Transaction] = []
    for t in transactions:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    if not unique:
        print(f"  warning: no transactions found in {path.name}")

    return unique


class PnbParser:
    def parse_pdf(self, path: Path, password: str | None) -> list[Transaction]:
        return parse_pdf(path, password)
