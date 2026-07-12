"""IDFC credit card statement parser."""

from __future__ import annotations

import re
from decimal import Decimal

from networthcsv.pipeline.parse.banks import register_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.string import DECIMAL_AMOUNT_TWO_PLACES
from networthcsv.utils.transactions import Transaction

_DATE_PREFIX = re.compile(
    r"^(\d{1,2}/(?:\d{1,2}|[A-Za-z]{3})/\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s+"
)
_DR_CR_SUFFIX = re.compile(r"\s+(DR|CR)\s*$", re.IGNORECASE)
_CR_SUFFIX = re.compile(r"\s+CR\s*$", re.IGNORECASE)
_FX_TAIL = re.compile(r"\s+USD\s+[\d,]+\.\d{2}\s*$", re.IGNORECASE)


def _parse_transaction_line(line: str) -> tuple | None:
    stripped = line.strip()
    if not stripped:
        return None

    date_match = _DATE_PREFIX.match(stripped)
    if date_match is None:
        return None

    txn_date = parse_date_string(date_match.group(1))
    if txn_date is None:
        return None

    rest = stripped[date_match.end() :].strip()
    direction = "DR"

    dr_cr_match = _DR_CR_SUFFIX.search(rest)
    if dr_cr_match is not None:
        direction = dr_cr_match.group(1).upper()
        rest = rest[: dr_cr_match.start()].strip()
    elif _CR_SUFFIX.search(rest) is not None:
        direction = "CR"
        rest = _CR_SUFFIX.sub("", rest).strip()

    amount_matches = list(DECIMAL_AMOUNT_TWO_PLACES.finditer(rest))
    if not amount_matches:
        return None

    last_amount = amount_matches[-1]
    amount = Decimal(last_amount.group(0).replace(",", ""))
    description = rest[: last_amount.start()].strip()
    description = _FX_TAIL.sub("", description).strip()

    if not description:
        return None

    return txn_date, description, amount, direction


@register_parser("idfc", "wow")
class IdfcWowStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        rows: list[Transaction] = []
        for line in text.split("\n"):
            parsed = _parse_transaction_line(line)
            if parsed is None:
                continue
            txn_date, description, amount, direction = parsed
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
