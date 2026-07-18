"""IndusInd credit card statement parser."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import (
    line_has_dr_cr_marker,
    make_transaction,
    parse_dated_amount_line,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


@register_parser("indusind")
@register_parser("indusind", "default")
@register_parser("indusind", "auraedge")
@register_parser("indusind", "amex-epay")
class IndusindStatementParser:
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
            stripped = line.strip()
            if stripped.upper().startswith("TOTAL"):
                continue
            if " To " in stripped:
                continue
            if not line_has_dr_cr_marker(line):
                continue
            parsed = parse_dated_amount_line(line)
            if parsed is None:
                continue
            txn_date, description, amount, direction = parsed
            parts = description.rsplit(None, 1)
            if len(parts) == 2 and parts[1].isdigit():
                description = parts[0]
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
