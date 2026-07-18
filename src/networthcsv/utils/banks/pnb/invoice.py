"""PNB credit card statement invoice number extraction."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.dates import label_regex
from networthcsv.utils.banks.pnb.common import INVOICE_NO_LABEL

_INVOICE_NUMBER = re.compile(r"\d{4}CC\d+", re.IGNORECASE)


def extract_invoice_number(text: str) -> str | None:
    """Return the PNB invoice number after ``Invoice No :``, if present."""
    match = label_regex(INVOICE_NO_LABEL).search(text)
    if match is None:
        return None
    tail = text[match.end() : match.end() + 500]
    for line in tail.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        found = _INVOICE_NUMBER.search(stripped)
        if found is not None:
            return found.group(0).upper()
    return None
