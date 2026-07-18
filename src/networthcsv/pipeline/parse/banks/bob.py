"""Bank of Baroda credit card statement parser."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import make_transaction
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

# 08/10/2024 R88001 MUNICIPAL SERVICE FEE  0  INR  50.00  50.00 DR
_LINE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})\s+(\S+)\s+(.+)\s+([\d,]+\.\d{2})\s+(DR|CR)\s*$",
    re.IGNORECASE,
)


@register_parser("bob")
@register_parser("bob", "default")
@register_parser("bob", "easy")
class BobStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        _ = account
        rows: list[Transaction] = []
        for raw in text.splitlines():
            match = _LINE.match(raw.strip())
            if match is None:
                continue
            txn_date = parse_date_string(match.group(1))
            if txn_date is None:
                continue
            ref_no = match.group(2).strip()
            description = match.group(3).strip()
            description = re.sub(
                r"\s+\d+\s+INR\s+[\d,]+\.\d{2}\s*$",
                "",
                description,
                flags=re.IGNORECASE,
            ).strip()
            description = re.sub(
                r"\s+INR\s+[\d,]+\.\d{2}\s*$",
                "",
                description,
                flags=re.IGNORECASE,
            ).strip()
            amount = Decimal(match.group(4).replace(",", ""))
            direction = match.group(5).upper()
            rows.append(
                make_transaction(
                    txn_date=txn_date,
                    description=description,
                    amount=amount,
                    direction=direction,
                    source_file=source_file,
                    ref_no=ref_no,
                )
            )
        return rows
