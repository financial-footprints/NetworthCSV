"""HDFC credit card statement parser."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

_TRANSACTION_LINE = re.compile(
    r"^(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s+(DR|CR)\s+",
    re.MULTILINE,
)


@register_parser("hdfc")
class HdfcStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        rows: list[Transaction] = []
        for match in _TRANSACTION_LINE.finditer(text):
            txn_date = parse_date_string(match.group(1))
            if txn_date is None:
                continue
            description = match.group(2).strip()
            amount = Decimal(match.group(3).replace(",", ""))
            direction = match.group(4).upper()
            credited = amount if direction == "CR" else Decimal("0")
            debited = amount if direction == "DR" else Decimal("0")
            rows.append(
                Transaction(
                    date=txn_date,
                    description=description,
                    credited=credited,
                    debited=debited,
                    source_file=source_file,
                )
            )
        return rows
