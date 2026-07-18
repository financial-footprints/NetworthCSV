"""Shared helpers for statement transaction line parsing."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

_LineParser = Callable[[str], tuple[date, str, Decimal, str] | None]

_AMOUNT = re.compile(
    r"(?:Rs\.?\s*)?([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_DR_CR_TOKEN = re.compile(r"\b(DR|CR|Dr|Cr)\b")
_DD_MON_RS_DR_CR_LINE = re.compile(
    r"^\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(.+?)\s+Rs\.?\s*([\d,]+(?:\.\d{1,2})?)\s*(Dr|Cr)\s*$",
    re.IGNORECASE,
)
_DATE_PREFIXES = (
    re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4})\s+"),
    re.compile(r"^(\d{1,2}-\d{1,2}-\d{2,4})\s+"),
    re.compile(r"^(\d{1,2}-[A-Za-z]{3}-\d{2,4})\s+"),
    re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+"),
)


def credited_debited(amount: Decimal, direction: str) -> tuple[Decimal, Decimal]:
    if direction.upper() == "CR":
        return amount, Decimal("0")
    return Decimal("0"), amount


def make_transaction(
    *,
    txn_date: date,
    description: str,
    amount: Decimal,
    direction: str,
    source_file: str,
    ref_no: str | None = None,
) -> Transaction:
    credited, debited = credited_debited(amount, direction)
    return Transaction(
        date=txn_date,
        description=description,
        credited=credited,
        debited=debited,
        source_file=source_file,
        ref_no=ref_no,
    )


def split_direction_suffix(rest: str) -> tuple[str, str]:
    """Return (text_without_direction, DR|CR). Default DR when bare amount."""
    matches = list(_DR_CR_TOKEN.finditer(rest))
    if not matches:
        return rest.strip(), "DR"
    last = matches[-1]
    direction = "CR" if last.group(1).upper().startswith("C") else "DR"
    return rest[: last.start()].strip(), direction


def parse_dated_amount_line(line: str) -> tuple[date, str, Decimal, str] | None:
    """Parse ``DATE description amount [Dr|Cr]`` style lines."""
    stripped = line.strip()
    if not stripped:
        return None

    date_match = None
    for pattern in _DATE_PREFIXES:
        date_match = pattern.match(stripped)
        if date_match is not None:
            break
    if date_match is None:
        return None

    txn_date = parse_date_string(date_match.group(1))
    if txn_date is None:
        return None

    rest = stripped[date_match.end() :].strip()
    rest, direction = split_direction_suffix(rest)
    amount_matches = list(_AMOUNT.finditer(rest))
    if not amount_matches:
        return None

    last = amount_matches[-1]
    amount = Decimal(last.group(1).replace(",", ""))
    description = rest[: last.start()].strip()
    description = re.sub(r"\s*Rs\.?\s*$", "", description, flags=re.IGNORECASE).strip()
    if not description:
        return None
    return txn_date, description, amount, direction


def line_has_dr_cr_marker(line: str) -> bool:
    return _DR_CR_TOKEN.search(line) is not None


def parse_dd_mon_rs_dr_cr_line(
    line: str,
) -> tuple[date, str, Decimal, str] | None:
    """Parse ``DD Mon YY DESCRIPTION Rs. amount Dr|Cr`` lines."""
    match = _DD_MON_RS_DR_CR_LINE.match(line.strip())
    if match is None:
        return None
    txn_date = parse_date_string(match.group(1))
    if txn_date is None:
        return None
    description = match.group(2).strip()
    if not description:
        return None
    amount = Decimal(match.group(3).replace(",", ""))
    direction = "CR" if match.group(4).upper().startswith("C") else "DR"
    return txn_date, description, amount, direction


def parse_stop_at_end_lines(
    text: str,
    line_parser: _LineParser,
    *,
    account: ResolvedAccount,
    source_file: str,
    stop_marker: str = "End of Transactions",
) -> list[Transaction]:
    """Parse transaction lines until ``stop_marker`` appears in a line."""
    _ = account
    rows: list[Transaction] = []
    for line in text.splitlines():
        if stop_marker in line:
            break
        parsed = line_parser(line)
        if parsed is None:
            continue
        txn_date, description, amount, direction = parsed
        description = description.replace("Rs.", "").strip()
        if not description:
            continue
        rows.append(
            make_transaction(
                txn_date=txn_date,
                description=description,
                amount=amount,
                direction=direction,
                source_file=source_file,
            )
        )
    return rows
