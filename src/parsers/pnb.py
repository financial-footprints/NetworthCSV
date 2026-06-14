"""Parse transaction rows from PNB credit card statement text."""

from __future__ import annotations

import re

from src.core.amounts import make_transaction
from src.core.dates import parse_date_dmy_mon
from src.core.transactions import Transaction
from src.parsers.common import finalize_parse, warn_if_empty_text

# Transaction rows: DD-MMM-YYYY  DD-MMM-YYYY  <description>  <amount> [Cr]
_TXN_ROW = re.compile(
    r"(\d{2}-[A-Za-z]{3}-\d{4})\s+\d{2}-[A-Za-z]{3}-\d{4}\s+(.+?)\s+([\d,]+\.\d{2})(\s+Cr)?\s*$",
    re.IGNORECASE,
)

# Marks the start of the transaction table
_SECTION_HEADERS = ("Transaction Date", "Trnx Details")

# Marks the end of the transaction table
_FOOTER_MARKERS = ("Total Purchase", "End of Statement", "Total Taxable Value")


def _find_section_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (start_idx, end_idx) of the transaction table lines."""
    start = None
    for i, line in enumerate(lines):
        if start is None and any(kw in line for kw in _SECTION_HEADERS):
            start = i + 1
            continue
        if start is not None and any(marker in line for marker in _FOOTER_MARKERS):
            return start, i

    if start is not None:
        return start, len(lines)
    return 0, len(lines)


def _try_match_row(line: str, source_file: str) -> Transaction | None:
    m = _TXN_ROW.search(line)
    if not m:
        return None
    date_raw, description, amount_raw, credit_suffix = m.groups()
    txn_date = parse_date_dmy_mon(date_raw)
    if txn_date is None:
        return None
    return make_transaction(
        txn_date,
        description,
        amount_raw,
        credit_suffix is not None,
        source_file,
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


class PnbParser:
    def parse_text(self, text: str, *, source_file: str) -> list[Transaction]:
        """Extract all transactions from a PNB credit card statement text."""
        if warn_if_empty_text(text, source_file):
            return []
        return finalize_parse(_extract_from_text(text, source_file), source_file)
