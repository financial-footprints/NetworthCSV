"""ICICI credit card statement parser (CSV exports)."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.icici.csv import (
    icici_csv_rows_to_transactions,
    parse_icici_csv_rows,
)
from networthcsv.utils.transactions import Transaction


@register_parser("icici")
@register_parser("icici", "default")
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
        # CSV exports include this section marker; PDF text does not.
        if "Transaction Details:" not in text:
            return []
        rows = parse_icici_csv_rows(text)
        return icici_csv_rows_to_transactions(rows, source_file=source_file)
