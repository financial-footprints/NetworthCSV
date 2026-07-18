"""CSB credit card statement parser."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import (
    make_transaction,
    parse_dd_mon_rs_dr_cr_line,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


@register_parser("csb")
@register_parser("csb", "default")
@register_parser("csb", "edge")
class CsbStatementParser:
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
            if "End of Transactions" in line:
                break
            parsed = parse_dd_mon_rs_dr_cr_line(line)
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
