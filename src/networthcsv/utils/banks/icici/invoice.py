"""ICICI credit card statement invoice number extraction."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.dates import label_regex

_INVOICE_LABELS = ("Invoice No:", "Invoice No :")
_INVOICE_NUMBER = re.compile(r"\d{10,}")


def extract_invoice_number(text: str) -> str | None:
    """Return the ICICI invoice number after an ``Invoice No`` label, if present."""
    for label in _INVOICE_LABELS:
        match = label_regex(label).search(text)
        if match is None:
            continue
        tail = text[match.end() : match.end() + 500]
        for line in tail.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            found = _INVOICE_NUMBER.search(stripped)
            if found is not None:
                return found.group(0)
    return None
