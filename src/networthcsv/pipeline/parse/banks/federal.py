"""Federal Bank credit card statement parser."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.pipeline.parse.banks.common import (
    parse_dated_amount_line,
    parse_dd_mon_rs_dr_cr_line,
    parse_stop_at_end_lines,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.transactions import Transaction

_DMY_HYPHEN_DR_CR_LINE = re.compile(
    r"^\s*(\d{1,2}-\d{1,2}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s*(Dr|Cr)\s*$",
    re.IGNORECASE,
)
_LineParser = Callable[[str], tuple[date, str, Decimal, str] | None]


def _parse_dmy_hyphen_dr_cr_line(
    line: str,
) -> tuple[date, str, Decimal, str] | None:
    """Parse ``DD-MM-YYYY DESCRIPTION amount Dr|Cr`` lines (Federal Signet layout)."""
    match = _DMY_HYPHEN_DR_CR_LINE.match(line.strip())
    if match is None:
        return None
    txn_date = parse_date_string(match.group(1))
    if txn_date is None:
        return None
    description = match.group(2).strip()
    if not description:
        return None
    amount = Decimal(match.group(3).replace(",", ""))
    direction = "CR" if match.group(4).upper().startswith("C") else "DR"
    return txn_date, description, amount, direction


def _line_parser_for_variant(variant: str | None) -> _LineParser:
    if variant == "signet":
        return _parse_dmy_hyphen_dr_cr_line
    if variant == "edge":
        return parse_dd_mon_rs_dr_cr_line
    return parse_dated_amount_line


@register_parser("federal")
@register_parser("federal", "signet")
@register_parser("federal", "edge")
class FederalStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        return parse_stop_at_end_lines(
            text,
            _line_parser_for_variant(account.variant),
            account=account,
            source_file=source_file,
        )
