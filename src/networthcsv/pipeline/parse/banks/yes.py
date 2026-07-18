"""YES Bank credit card statement parser."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import (
    make_transaction,
    parse_dated_amount_line,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


@register_parser("yes")
@register_parser("yes", "default")
@register_parser("yes", "ace")
class YesStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        _ = account
        rows: list[Transaction] = []
        for line in text.splitlines():
            lower = line.lower()
            if "nil transaction" in lower:
                continue
            parsed = parse_dated_amount_line(line)
            if parsed is None:
                continue
            txn_date, description, amount, direction = parsed
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
