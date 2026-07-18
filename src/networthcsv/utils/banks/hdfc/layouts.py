"""Shared HDFC statement layout detectors and parsers.

v2 is the bank-wide styling/consistency layout (stacked Account Summary,
split ``Statement`` / ``Date:`` header, optional ``DUPLICATE STATEMENT``).
v1 is the prior classic / variant-specific layouts handled by each handler.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from networthcsv.utils.banks.helpers.dates import find_label, first_date_in_text
from networthcsv.utils.banks.helpers.tables import (
    amounts_with_positions,
    summary_table_row,
)
from networthcsv.utils.billing_period import approximate_period_start_from_statement_end

HdfcLayoutId = Literal["v1", "v2"]

_AAN_EXPLICIT = re.compile(r"\bAAN\s*:?\s*(\d{10,})\b", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\d{13,}")
_STATEMENT_DATE_SPLIT = re.compile(r"Statement\s*\n\s*Date\s*:", re.IGNORECASE)
_STACKED_OPENING_BALANCE = re.compile(
    r"Account Summary[\s\S]{0,240}?Opening\s*\n\s*Balance\b",
    re.IGNORECASE,
)


def is_hdfc_v2(text: str) -> bool:
    """Detect the bank-wide v2 / consistency-guideline statement layout."""
    if "DUPLICATE STATEMENT" in text.upper():
        return True
    if _STATEMENT_DATE_SPLIT.search(text) is not None:
        return True
    if _STACKED_OPENING_BALANCE.search(text) is not None:
        return True
    return False


def detect_hdfc_layout(text: str) -> HdfcLayoutId:
    return "v2" if is_hdfc_v2(text) else "v1"


def extract_aan(text: str) -> str | None:
    """Return HDFC Alternate Account Number (AAN) digits when present."""
    explicit = _AAN_EXPLICIT.search(text)
    if explicit is not None:
        return explicit.group(1)
    alt = find_label(text, "Alternate Account Number")
    if alt is None:
        return None
    window = text[alt.end() : alt.end() + 400]
    match = _LONG_DIGITS.search(window)
    if match is None:
        return None
    return match.group(0)


def _account_summary_row_amounts(text: str) -> list[str] | None:
    match = find_label(text, "Account Summary")
    if match is None:
        return None
    for line in text[match.end() : match.end() + 1200].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        amounts = amounts_with_positions(stripped)
        if len(amounts) >= 3:
            return [amount for amount, _pos in amounts]
    return None


def account_summary_opening(text: str) -> str | None:
    amounts = _account_summary_row_amounts(text)
    if amounts is not None:
        return amounts[0]
    return summary_table_row(text, after="Account Summary", which=1, column="opening")


def account_summary_total_dues(text: str) -> str | None:
    amounts = _account_summary_row_amounts(text)
    if amounts is not None:
        return amounts[-1]
    return summary_table_row(text, after="Account Summary", which=1, column="closing")


def payment_due_total_dues(text: str) -> str | None:
    match = find_label(text, "Payment Due Date")
    if match is None:
        return None
    for line in text[match.end() : match.end() + 400].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if first_date_in_text(stripped) is None:
            continue
        amounts = amounts_with_positions(stripped)
        if len(amounts) >= 2:
            return amounts[0][0]
    return None


def approximate_period_if_needed(
    period_start: date | None, period_end: date | None
) -> tuple[date | None, date | None]:
    if period_start is not None and period_end is not None:
        return period_start, period_end
    if period_end is None:
        return None, None
    return approximate_period_start_from_statement_end(period_end), period_end
