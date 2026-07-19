"""CSB credit card statement parser."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import (
    parse_dd_mon_rs_dr_cr_line,
    parse_stop_at_end_lines,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


@register_parser("csb")
@register_parser("csb", "edge")
class CsbStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        return parse_stop_at_end_lines(
            text,
            parse_dd_mon_rs_dr_cr_line,
            source_file=source_file,
        )
