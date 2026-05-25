"""Parse transaction rows from IDFC FIRST Bank credit card statement PDFs."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from src.bank.base import Transaction

_DATE_SLASH = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_DATE_MON = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{2}$")
_AMOUNT = re.compile(r"^([\d,]+\.\d{2})\s+(DR|CR)$", re.IGNORECASE)
_FX = re.compile(r"^USD\s+[\d.]+", re.IGNORECASE)

# Single-line: date + description + optional USD + amount + DR|CR
_TXN_LINE_SLASH = re.compile(
    (
        r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+"
        r"(?:USD\s+[\d.]+\s+)?"
        r"([\d,]+\.\d{2})\s+(DR|CR)\s*$"
    ),
    re.IGNORECASE,
)
_TXN_LINE_MON = re.compile(
    (
        r"^(\d{2}\s+[A-Za-z]{3}\s+\d{2})\s+(.+?)\s+"
        r"(?:USD\s+[\d.]+\s+)?"
        r"([\d,]+\.\d{2})\s+(DR|CR)\s*$"
    ),
    re.IGNORECASE,
)

_SECTION_START = "YOUR TRANSACTIONS"
_SECTION_END_MARKERS = ("SPECIAL BENEFITS", "IMPORTANT INFORMATION")

_SKIP_SUBSTRINGS = (
    "Transaction Date",
    "Transactional Details",
    "Transaction Details",
    "EMI Eligibility",
    "FX Transactions",
    "Amount (r)",
    "Amount (In INR)",
    "Card Number:",
    "Purchases, EMIs",
    "Payments & Refunds",
)

_MAX_DESCRIPTION_LEN = 120
_DEBUG = os.environ.get("CCPARSER_IDFC_DEBUG", "").strip() in ("1", "true", "yes")


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


def _parse_date_slash(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_date_mon(raw: str) -> date | None:
    normalised = raw[:3] + raw[3:6].title() + raw[6:]
    try:
        return datetime.strptime(normalised, "%d %b %y").date()
    except ValueError:
        return None


def _parse_date_line(line: str) -> date | None:
    if _DATE_SLASH.match(line):
        return _parse_date_slash(line)
    if _DATE_MON.match(line):
        return _parse_date_mon(line)
    return None


def _parse_amount(raw: str, is_credit: bool) -> tuple[Decimal, Decimal]:
    amount = Decimal(raw.replace(",", ""))
    if is_credit:
        return amount, Decimal(0)
    return Decimal(0), amount


def _is_valid_description(description: str) -> bool:
    if len(description) > _MAX_DESCRIPTION_LEN:
        return False
    lower = description.lower()
    if "statement period" in lower or "card number" in lower:
        return False
    return True


def _should_skip_line(line: str) -> bool:
    if not line:
        return True
    return any(skip in line for skip in _SKIP_SUBSTRINGS)


def _iter_section_lines(lines: list[str]) -> Iterator[list[str]]:
    """Yield transaction-section line slices per YOUR TRANSACTIONS block."""
    in_section = False
    section: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _SECTION_START in stripped:
            in_section = True
            section = []
            continue
        if not in_section:
            continue
        if any(marker in stripped for marker in _SECTION_END_MARKERS):
            if section:
                yield section
            in_section = False
            section = []
            continue
        section.append(stripped)

    if in_section and section:
        yield section


def _transaction_from_parts(
    txn_date: date,
    description: str,
    amount_raw: str,
    txn_type: str,
    source_file: str,
) -> Transaction | None:
    description = description.strip()
    if not _is_valid_description(description):
        return None
    is_credit = txn_type.upper() == "CR"
    credited, debited = _parse_amount(amount_raw, is_credit)
    return Transaction(
        date=txn_date,
        description=description,
        credited=credited,
        debited=debited,
        source_file=source_file,
    )


def _try_single_line(line: str, source_file: str) -> Transaction | None:
    for pattern in (_TXN_LINE_SLASH, _TXN_LINE_MON):
        m = pattern.match(line)
        if not m:
            continue
        date_raw, description, amount_raw, txn_type = m.groups()
        txn_date = _parse_date_slash(date_raw) if "/" in date_raw else _parse_date_mon(date_raw)
        if txn_date is None:
            return None
        return _transaction_from_parts(
            txn_date, description, amount_raw, txn_type, source_file
        )
    return None


def _parse_section_queue(section_lines: list[str], source_file: str) -> list[Transaction]:
    """Parse stacked layout: dates/descriptions first, amounts at end."""
    pending: list[tuple[date, str]] = []
    amounts: list[tuple[str, str]] = []
    current_date: date | None = None
    desc_parts: list[str] = []

    def flush_pending() -> None:
        nonlocal current_date, desc_parts
        if current_date is None:
            desc_parts = []
            return
        description = " ".join(desc_parts).strip()
        pending.append((current_date, description))
        current_date = None
        desc_parts = []

    for line in section_lines:
        if _should_skip_line(line):
            continue

        txn_date = _parse_date_line(line)
        if txn_date is not None:
            flush_pending()
            current_date = txn_date
            continue

        amount_m = _AMOUNT.match(line)
        if amount_m:
            amounts.append((amount_m.group(1), amount_m.group(2)))
            continue

        if _FX.match(line):
            continue

        if current_date is not None:
            desc_parts.append(line)

    flush_pending()

    transactions: list[Transaction] = []
    if len(pending) != len(amounts):
        if pending or amounts:
            print(
                f"  warning: transaction/amount count mismatch in {source_file} "
                + f"({len(pending)} rows, {len(amounts)} amounts)"
            )
        return transactions

    for (txn_date, description), (amount_raw, txn_type) in zip(pending, amounts):
        txn = _transaction_from_parts(
            txn_date, description, amount_raw, txn_type, source_file
        )
        if txn is not None:
            transactions.append(txn)

    return transactions


def _parse_section_lines(section_lines: list[str], source_file: str) -> list[Transaction]:
    """Try single-line matches first; fall back to queue parser for stacked layout."""
    single_line: list[Transaction] = []
    has_bare_date = False

    for line in section_lines:
        if _should_skip_line(line):
            continue
        txn = _try_single_line(line, source_file)
        if txn is not None:
            single_line.append(txn)
            continue
        if _parse_date_line(line) is not None:
            has_bare_date = True

    if single_line and not has_bare_date:
        return single_line

    return _parse_section_queue(section_lines, source_file)


def _extract_from_text(text: str, source_file: str) -> tuple[list[Transaction], bool]:
    """Parse transactions; return (rows, section_header_seen)."""
    lines = text.splitlines()
    sections = list(_iter_section_lines(lines))
    if not sections:
        return [], False

    transactions: list[Transaction] = []
    for section in sections:
        transactions.extend(_parse_section_lines(section, source_file))
    return transactions, True


def parse_pdf(path: Path, password: str | None) -> list[Transaction]:
    """Extract all transactions from an IDFC FIRST Bank credit card PDF statement."""
    pages = _extract_pages(path, password)
    if not pages:
        print(f"  warning: no text extracted from {path.name}")
        return []

    transactions: list[Transaction] = []
    saw_section = False

    for page_text in pages:
        page_txns, section_on_page = _extract_from_text(page_text, path.name)
        transactions.extend(page_txns)
        saw_section = saw_section or section_on_page

    seen: set[Transaction] = set()
    unique: list[Transaction] = []
    for t in transactions:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    if _DEBUG:
        removed = len(transactions) - len(unique)
        print(
            f"  debug {path.name}: raw={len(transactions)} "
            + f"unique={len(unique)} deduped={removed} section={saw_section}"
        )

    if saw_section and not unique:
        print(f"  warning: no transactions found in {path.name}")

    return unique


class IdfcParser:
    def parse_pdf(self, path: Path, password: str | None) -> list[Transaction]:
        return parse_pdf(path, password)
