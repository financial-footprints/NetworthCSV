"""HDFC credit card statement parser."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import make_transaction
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

# Annual / year-end: 16-May-2024  SAMPLE MERCHANT  100.00  DR  1234...
_ANNUAL_LINE = re.compile(
    r"^(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s+(DR|CR)\b",
    re.MULTILINE | re.IGNORECASE,
)

# Monthly: 14/05/2021 [HH:MM:SS] DESC  180.00[Cr]
_MONTHLY_LINE = re.compile(
    r"^\s*(\d{1,2}/\d{1,2}/\d{4})(?:\s+\d{1,2}:\d{2}:\d{2})?\s+(.+?)\s+"
    r"([\d,]+\.\d{2})\s*(Cr|CR|Dr|DR)?\s*$",
    re.MULTILINE,
)


def _direction_from_suffix(raw: str | None) -> str:
    if raw is None:
        return "DR"
    return "CR" if raw.upper().startswith("C") else "DR"


@register_parser("hdfc")
class HdfcStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        _ = account
        rows: list[Transaction] = []
        seen: set[tuple] = set()

        for match in _ANNUAL_LINE.finditer(text):
            txn_date = parse_date_string(match.group(1))
            if txn_date is None:
                continue
            description = match.group(2).strip()
            amount = Decimal(match.group(3).replace(",", ""))
            direction = match.group(4).upper()
            key = (txn_date, description, amount, direction)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                make_transaction(
                    txn_date=txn_date,
                    description=description,
                    amount=amount,
                    direction=direction,
                    source_file=source_file,
                )
            )

        for match in _MONTHLY_LINE.finditer(text):
            txn_date = parse_date_string(match.group(1))
            if txn_date is None:
                continue
            description = match.group(2).strip()
            if not description:
                continue
            amount = Decimal(match.group(3).replace(",", ""))
            direction = _direction_from_suffix(match.group(4))
            key = (txn_date, description, amount, direction)
            if key in seen:
                continue
            seen.add(key)
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
