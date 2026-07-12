"""Amount parsing and balance comparison helpers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from networthcsv.utils.string import (
    AMOUNT_TOKEN,
    CID_PATTERN,
    CURRENCY_AMOUNT_TOKEN,
)

DEFAULT_BALANCE_MATCH_TOLERANCE = Decimal("0.21")


def parse_amount_string(value: str) -> str | None:
    """Parse an Indian credit-card amount into a normalized decimal string."""
    stripped = value.strip()
    if not stripped:
        return None

    negative = False
    if stripped.startswith("(") and stripped.endswith(")"):
        negative = True
        stripped = stripped[1:-1].strip()
    if stripped.startswith("-"):
        negative = True
        stripped = stripped[1:].strip()

    stripped = re.sub(r"^(?:Rs\.?|INR|₹|[rC])\s*", "", stripped, flags=re.IGNORECASE)
    credit = bool(re.search(r"\bCr\b", stripped, re.IGNORECASE))
    debit = bool(re.search(r"\bDr\b", stripped, re.IGNORECASE))
    stripped = re.sub(
        r"\s*(?:Cr|Dr|CR|DR)\s*$", "", stripped, flags=re.IGNORECASE
    ).strip()
    stripped = stripped.replace(",", "")
    if not stripped:
        return None

    try:
        amount = Decimal(stripped)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    if credit:
        amount = -abs(amount)
    elif debit:
        amount = abs(amount)
    return format(amount, "f")


def balances_match(
    left: str,
    right: str,
    *,
    tolerance: Decimal | None = None,
) -> bool:
    """Return True when two balance strings agree within bank rounding tolerance."""
    threshold = DEFAULT_BALANCE_MATCH_TOLERANCE if tolerance is None else tolerance
    left_parsed = parse_amount_string(left)
    right_parsed = parse_amount_string(right)
    if left_parsed is None or right_parsed is None:
        return left == right
    return abs(Decimal(left_parsed) - Decimal(right_parsed)) <= threshold


def _is_inside_cid(text: str, index: int) -> bool:
    for match in CID_PATTERN.finditer(text):
        if match.start() <= index < match.end():
            return True
    return False


def first_amount_in_text(text: str) -> str | None:
    for match in AMOUNT_TOKEN.finditer(text):
        if _is_inside_cid(text, match.start()):
            continue
        parsed = parse_amount_string(match.group(0))
        if parsed is not None:
            return parsed
    return None


def amounts_with_positions(
    line: str,
    *,
    currency_only: bool = False,
) -> list[tuple[str, int]]:
    pattern = CURRENCY_AMOUNT_TOKEN if currency_only else AMOUNT_TOKEN
    found: list[tuple[str, int]] = []
    for match in pattern.finditer(line):
        if _is_inside_cid(line, match.start()):
            continue
        parsed = parse_amount_string(match.group(0))
        if parsed is not None:
            found.append((parsed, match.start()))
    return found


def first_not_none(*values: str | None) -> str | None:
    for value in values:
        if value is not None:
            return value
    return None
