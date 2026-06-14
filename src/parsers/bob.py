"""Parse transaction rows from BOBCARD credit card statement text."""

from __future__ import annotations

import re
from collections.abc import Iterator
from re import Match

from src.core.amounts import make_transaction
from src.core.dates import parse_date_dmy_slash
from src.core.env import env_flag
from src.core.transactions import Transaction
from src.parsers.common import finalize_parse, is_valid_description, warn_if_empty_text

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

_DEBUG = env_flag("CCPARSER_BOB_DEBUG")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _spans_overlap(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


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
    if not is_valid_description(description.strip()):
        return None
    txn_date = parse_date_dmy_slash(date_raw)
    if txn_date is None:
        return None
    return make_transaction(
        txn_date,
        description,
        amount_raw,
        txn_type.upper() == "CR",
        source_file,
        ref_no=ref_no,
    )


def _transaction_from_no_ref(m: Match[str], source_file: str) -> Transaction | None:
    date_raw, description, amount_raw, txn_type = m.groups()
    if not is_valid_description(description.strip()):
        return None
    txn_date = parse_date_dmy_slash(date_raw)
    if txn_date is None:
        return None
    return make_transaction(
        txn_date,
        description,
        amount_raw,
        txn_type.upper() == "CR",
        source_file,
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


class BobParser:
    def parse_text(self, text: str, *, source_file: str) -> list[Transaction]:
        """Extract all transactions from BOBCARD statement text."""
        if warn_if_empty_text(text, source_file):
            return []

        transactions = _extract_from_text(text, source_file)
        debug_label = None
        if _DEBUG:
            with_ref_count = sum(1 for t in transactions if t.ref_no)
            no_ref_count = len(transactions) - with_ref_count
            debug_label = f"(with_ref={with_ref_count}, no_ref={no_ref_count})"

        return finalize_parse(transactions, source_file, debug_label=debug_label)
