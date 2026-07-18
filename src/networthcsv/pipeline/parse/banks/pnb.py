"""PNB credit card statement parser."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import make_transaction
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

# 19-APR-2021 19-APR-2021 Payment Recd          780.00 Cr
# 21-APR-2021 23-APR-2021 GOVT FACILITY … 680.00
_LINE = re.compile(
    r"^(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(.+)$",
    re.IGNORECASE,
)
_AMOUNT_TAIL = re.compile(r"([\d,]+\.\d{2})\s*(Cr|Dr|CR|DR)?\s*$", re.IGNORECASE)


@register_parser("pnb")
@register_parser("pnb", "platinum")
class PnbStatementParser:
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
            stripped = raw.strip()
            if stripped.upper().startswith("TOTAL"):
                continue
            match = _LINE.match(stripped)
            if match is None:
                continue
            txn_date = parse_date_string(match.group(1))
            if txn_date is None:
                continue
            rest = match.group(3).strip()
            amount_match = _AMOUNT_TAIL.search(rest)
            if amount_match is None:
                continue
            amount = Decimal(amount_match.group(1).replace(",", ""))
            raw_dir = amount_match.group(2)
            direction = "CR" if raw_dir and raw_dir.upper().startswith("C") else "DR"
            description = rest[: amount_match.start()].strip()
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
