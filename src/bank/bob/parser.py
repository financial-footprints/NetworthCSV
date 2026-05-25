"""Parse transaction rows from BOBCARD credit card statement PDFs."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from re import Match

from pypdf import PdfReader

from src.bank.base import Transaction

# With ref: date  ref  particulars  [reward cols]  INR  amt  amt  DR|CR
_TXN_WITH_REF = re.compile(
    (
        r"(\d{2}/\d{2}/\d{4})\s+(\S+)\s+(.+?)\s+"
        + r"(?:-?\d+\s+)*INR\s+"
        + r"([\d,]+\.\d{2})\s+(?:[\d,]+\.\d{2})\s*(DR|CR)\b"
    ),
    re.IGNORECASE,
)

# No ref: date  particulars  INR  amt  amt  DR|CR (particulars = single token, e.g. BBPS-PAYMENT)
_TXN_NO_REF = re.compile(
    (
        r"(\d{2}/\d{2}/\d{4})\s+(\S+)\s+INR\s+"
        + r"([\d,]+\.\d{2})\s+(?:[\d,]+\.\d{2})\s*(DR|CR)\b"
    ),
    re.IGNORECASE,
)

_PRIMARY_CARD = re.compile(r"\(PRIMARY CARD\s*-\s*\d+\)", re.IGNORECASE)
_TABLE_END = re.compile(r"Transaction Details", re.IGNORECASE)
_CONTINUATION = re.compile(
    r"(?:रकम\s+)?Amount\s+(\d{2}/\d{2}/\d{4})\s+",
    re.IGNORECASE,
)
_ROW_START = re.compile(r"(?=\d{2}/\d{2}/\d{4}\s)")

_MAX_DESCRIPTION_LEN = 120
_DEBUG = os.environ.get("CCPARSER_BOB_DEBUG", "").strip() in ("1", "true", "yes")


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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_amount(raw: str, is_credit: bool) -> tuple[Decimal, Decimal]:
    amount = Decimal(raw.replace(",", ""))
    if is_credit:
        return amount, Decimal(0)
    return Decimal(0), amount


def _parse_date(date_raw: str) -> datetime | None:
    try:
        return datetime.strptime(date_raw, "%d/%m/%Y")
    except ValueError:
        return None


def _spans_overlap(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def _is_valid_description(description: str) -> bool:
    if len(description) > _MAX_DESCRIPTION_LEN:
        return False
    if "statement period" in description.lower():
        return False
    return True


def _looks_like_ref(ref_no: str) -> bool:
    """Ref tokens look like R00935 or numeric ids, not BBPS-PAYMENT."""
    upper = ref_no.upper()
    if "PAYMENT" in upper or "BBPS" in upper:
        return False
    return bool(re.match(r"^R\d", ref_no, re.IGNORECASE)) or ref_no.isdigit()


def _region_fully_covered(start: int, end: int, covered: list[tuple[int, int]]) -> bool:
    return any(start >= cov_start and end <= cov_end for cov_start, cov_end in covered)


def _iter_table_sections(normalized: str) -> Iterator[str]:
    """Yield transaction-table slices only (excludes statement header)."""
    covered: list[tuple[int, int]] = []
    sections: list[str] = []

    def add_section(start: int, end: int) -> None:
        if start >= end or _region_fully_covered(start, end, covered):
            return
        sections.append(normalized[start:end])
        covered.append((start, end))

    for m in _PRIMARY_CARD.finditer(normalized):
        region_start = m.end()
        end_m = _TABLE_END.search(normalized, region_start)
        region_end = end_m.start() if end_m else len(normalized)
        add_section(region_start, region_end)

    for m in _CONTINUATION.finditer(normalized):
        region_start = m.start(1)
        end_m = _TABLE_END.search(normalized, region_start)
        region_end = end_m.start() if end_m else len(normalized)
        add_section(region_start, region_end)

    if sections:
        yield from sections
    else:
        yield normalized


def _iter_row_chunks(section: str) -> Iterator[str]:
    """Split a table section into one chunk per transaction row (by leading date)."""
    starts = [m.start() for m in _ROW_START.finditer(section)]
    if not starts:
        return
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(section)
        chunk = section[start:end].strip()
        if chunk:
            yield chunk


def _transaction_from_with_ref(m: Match[str], source_file: str) -> Transaction | None:
    date_raw, ref_no, description, amount_raw, txn_type = m.groups()
    if not _looks_like_ref(ref_no):
        return None
    description = description.strip()
    if not _is_valid_description(description):
        return None
    parsed = _parse_date(date_raw)
    if parsed is None:
        return None
    is_credit = txn_type.upper() == "CR"
    credited, debited = _parse_amount(amount_raw, is_credit)
    return Transaction(
        date=parsed.date(),
        description=description,
        credited=credited,
        debited=debited,
        source_file=source_file,
        ref_no=ref_no,
    )


def _transaction_from_no_ref(m: Match[str], source_file: str) -> Transaction | None:
    date_raw, description, amount_raw, txn_type = m.groups()
    description = description.strip()
    if not _is_valid_description(description):
        return None
    parsed = _parse_date(date_raw)
    if parsed is None:
        return None
    is_credit = txn_type.upper() == "CR"
    credited, debited = _parse_amount(amount_raw, is_credit)
    return Transaction(
        date=parsed.date(),
        description=description,
        credited=credited,
        debited=debited,
        source_file=source_file,
        ref_no=None,
    )


def _extract_matches_from_section(section: str, source_file: str) -> list[Transaction]:
    transactions: list[Transaction] = []
    for chunk in _iter_row_chunks(section):
        with_ref_spans: list[tuple[int, int]] = []

        for m in _TXN_WITH_REF.finditer(chunk):
            txn = _transaction_from_with_ref(m, source_file)
            if txn is not None:
                transactions.append(txn)
                with_ref_spans.append((m.start(), m.end()))

        for m in _TXN_NO_REF.finditer(chunk):
            if _spans_overlap(m.start(), m.end(), with_ref_spans):
                continue
            txn = _transaction_from_no_ref(m, source_file)
            if txn is not None:
                transactions.append(txn)

    return transactions


def _extract_from_text(text: str, source_file: str) -> list[Transaction]:
    """Parse transactions from a block of extracted text."""
    normalized = _normalize_text(text)
    transactions: list[Transaction] = []
    for section in _iter_table_sections(normalized):
        transactions.extend(_extract_matches_from_section(section, source_file))
    return transactions


def parse_pdf(path: Path, password: str | None) -> list[Transaction]:
    """Extract all transactions from a BOBCARD credit card PDF statement."""
    pages = _extract_pages(path, password)
    if not pages:
        print(f"  warning: no text extracted from {path.name}")
        return []

    transactions: list[Transaction] = []
    for page_text in pages:
        transactions.extend(_extract_from_text(page_text, path.name))

    with_ref_count = sum(1 for t in transactions if t.ref_no)
    no_ref_count = len(transactions) - with_ref_count

    seen: set[Transaction] = set()
    unique: list[Transaction] = []
    for t in transactions:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    if _DEBUG:
        removed = len(transactions) - len(unique)
        print(
            (
                f"  debug {path.name}: raw={len(transactions)} "
                + f"(with_ref={with_ref_count}, no_ref={no_ref_count}) "
                + f"unique={len(unique)} deduped={removed}"
            )
        )

    if not unique:
        print(f"  warning: no transactions found in {path.name}")

    return unique


class BobParser:
    def parse_pdf(self, path: Path, password: str | None) -> list[Transaction]:
        return parse_pdf(path, password)
