"""Shared compiled regex patterns for statement text parsing."""

from __future__ import annotations

import re

AMOUNT_TOKEN = re.compile(
    r"(?:"
    r"\(?\s*"
    r"(?:Rs\.?|INR|₹|[rC])\s*"
    r")?"
    r"(-?\d[\d,]*(?:\.\d+)?|\.\d+)"
    r"\s*"
    r"(?:Cr|Dr|CR|DR)?"
    r"\s*\)?",
    re.IGNORECASE,
)

CURRENCY_AMOUNT_TOKEN = re.compile(
    r"(?:"
    r"\(?\s*"
    r"(?:Rs\.?|INR|₹|[rC])\s*"
    r")?"
    r"(-?\d[\d,]*\.\d+|\.\d+)"
    r"\s*"
    r"(?:Cr|Dr|CR|DR)?"
    r"\s*\)?",
    re.IGNORECASE,
)

DECIMAL_AMOUNT_TWO_PLACES = re.compile(r"[\d,]+\.\d{2}")

CID_PATTERN = re.compile(r"\(cid:\d+\)", re.IGNORECASE)
