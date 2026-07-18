"""HDFC Swiggy layout routing: v1 legacy modern header, v2 shared HDFC guideline."""

from __future__ import annotations

import re
from typing import Literal, Protocol

from networthcsv.utils.banks.helpers.dates import find_label
from networthcsv.utils.banks.helpers.tables import amounts_with_positions
from networthcsv.utils.banks.hdfc.layouts import (
    account_summary_opening,
    account_summary_total_dues,
    detect_hdfc_layout,
    is_hdfc_v2,
    payment_due_total_dues,
)

SwiggyLayoutId = Literal["v1", "v2"]


class SwiggyLayout(Protocol):
    layout_id: SwiggyLayoutId

    def get_opening_balance(self, text: str) -> str | None: ...

    def get_closing_balance(self, text: str) -> str | None: ...


def detect_swiggy_layout(text: str) -> SwiggyLayoutId:
    """v2 = shared HDFC guideline layout; v1 = legacy TOTAL AMOUNT DUE header."""
    if is_hdfc_v2(text):
        return "v2"
    upper = text.upper()
    if find_label(text, "Billing Period") is not None:
        return "v1"
    if find_label(text, "PREVIOUS STATEMENT DUES") is not None:
        return "v1"
    if find_label(text, "TOTAL AMOUNT DUE", limit=1500) is not None:
        return "v1"
    # Prefer the bank-wide guideline layout when signals are ambiguous.
    if detect_hdfc_layout(text) == "v2" or "ACCOUNT SUMMARY" in upper:
        return "v2"
    return "v1"


def _previous_statement_dues_opening(text: str) -> str | None:
    match = find_label(text, "PREVIOUS STATEMENT DUES")
    if match is None:
        return None
    for line in text[match.end() : match.end() + 600].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        amounts = amounts_with_positions(stripped)
        if len(amounts) >= 3:
            return amounts[0][0]
    return None


def _modern_total_amount_due(text: str) -> str | None:
    """Closing from TOTAL AMOUNT DUE using cross-line find_label (v1 only)."""
    match = find_label(text, "TOTAL AMOUNT DUE", limit=1500)
    if match is None:
        return None
    prefix = text[max(0, match.start() - 40) : match.start()]
    if re.search(r"(?:than|the|less)\s+[\"']?\s*$", prefix, re.IGNORECASE):
        return None
    window = text[match.end() : match.end() + 400]
    for line in window.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        amounts = amounts_with_positions(stripped)
        if amounts:
            return amounts[0][0]
    return None


class SwiggyV1Layout:
    """Legacy Swiggy modern header (TOTAL AMOUNT DUE + PREVIOUS STATEMENT DUES)."""

    layout_id: SwiggyLayoutId = "v1"

    def get_opening_balance(self, text: str) -> str | None:
        return _previous_statement_dues_opening(text)

    def get_closing_balance(self, text: str) -> str | None:
        return _modern_total_amount_due(text)


class SwiggyV2Layout:
    """Shared HDFC v2 guideline layout."""

    layout_id: SwiggyLayoutId = "v2"

    def get_opening_balance(self, text: str) -> str | None:
        return account_summary_opening(text)

    def get_closing_balance(self, text: str) -> str | None:
        return account_summary_total_dues(text) or payment_due_total_dues(text)


_V1 = SwiggyV1Layout()
_V2 = SwiggyV2Layout()


def get_swiggy_layout(text: str) -> SwiggyLayout:
    if detect_swiggy_layout(text) == "v2":
        return _V2
    return _V1
