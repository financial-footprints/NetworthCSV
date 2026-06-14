"""Parse transaction rows from IDFC FIRST Bank credit card statement text."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date

from src.core.amounts import make_transaction
from src.core.dates import parse_date_dmy_mon_short, parse_date_dmy_slash
from src.core.env import env_flag
from src.core.transactions import Transaction
from src.parsers.common import finalize_parse, is_valid_description, warn_if_empty_text

logger = logging.getLogger(__name__)

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

_IDFC_REJECT_SUBSTRINGS = ("statement period", "card number")
_DEBUG = env_flag("CCPARSER_IDFC_DEBUG")


def _parse_date_line(line: str) -> date | None:
    if _DATE_SLASH.match(line):
        return parse_date_dmy_slash(line)
    if _DATE_MON.match(line):
        return parse_date_dmy_mon_short(line)
    return None


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
    if not is_valid_description(description.strip(), reject_substrings=_IDFC_REJECT_SUBSTRINGS):
        return None
    return make_transaction(
        txn_date,
        description,
        amount_raw,
        txn_type.upper() == "CR",
        source_file,
    )


def _try_single_line(line: str, source_file: str) -> Transaction | None:
    for pattern in (_TXN_LINE_SLASH, _TXN_LINE_MON):
        m = pattern.match(line)
        if not m:
            continue
        date_raw, description, amount_raw, txn_type = m.groups()
        txn_date = parse_date_dmy_slash(date_raw) if "/" in date_raw else parse_date_dmy_mon_short(date_raw)
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
            logger.warning(
                "transaction/amount count mismatch in %s (%d rows, %d amounts)",
                source_file,
                len(pending),
                len(amounts),
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


class IdfcParser:
    def parse_text(self, text: str, *, source_file: str) -> list[Transaction]:
        """Extract all transactions from an IDFC FIRST Bank credit card statement text."""
        if warn_if_empty_text(text, source_file):
            return []

        transactions, saw_section = _extract_from_text(text, source_file)
        debug_label = f"section={saw_section}" if _DEBUG else None
        return finalize_parse(
            transactions,
            source_file,
            saw_section=saw_section,
            debug_label=debug_label,
        )
