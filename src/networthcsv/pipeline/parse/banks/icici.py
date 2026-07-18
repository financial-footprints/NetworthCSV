"""ICICI credit card statement parser (CSV exports and TXT)."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import make_transaction
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.banks.icici.csv import (
    icici_csv_rows_to_transactions,
    parse_icici_csv_rows,
)
from networthcsv.utils.transactions import Transaction

# 15/09/2021 88472910561 COOPERATIVE STORE … 275.50
# 20/09/2021 88472910562 BBPS Payment received 0 1,380.00 CR
_TXT_LINE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})\s+(\d+)\s+(.+?)\s+([\d,]+\.\d{2})\s*(CR|DR)?\s*$",
    re.IGNORECASE,
)


def _parse_icici_txt(text: str, *, source_file: str) -> list[Transaction]:
    rows: list[Transaction] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        match = _TXT_LINE.match(stripped)
        if match is None:
            continue
        txn_date = parse_date_string(match.group(1))
        if txn_date is None:
            continue
        ref_no = match.group(2).strip()
        description = match.group(3).strip()
        # Drop trailing reward-point integers from description when present.
        description = re.sub(r"\s+\d+\s*$", "", description).strip()
        if not description:
            continue
        amount = Decimal(match.group(4).replace(",", ""))
        raw_dir = match.group(5)
        direction = "CR" if raw_dir and raw_dir.upper() == "CR" else "DR"
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


@register_parser("icici")
@register_parser("icici", "coral")
@register_parser("icici", "platinum")
@register_parser("icici", "amazon")
class IciciStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        _ = account
        if "Transaction Details:" in text:
            rows = parse_icici_csv_rows(text)
            return icici_csv_rows_to_transactions(rows, source_file=source_file)
        return _parse_icici_txt(text, source_file=source_file)
