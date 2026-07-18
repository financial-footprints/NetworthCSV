"""PNB v2 stacked label / value block parsing."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.amounts import first_amount_in_text
from networthcsv.utils.banks.helpers.dates import label_regex, parse_date_string
from networthcsv.utils.banks.pnb.common import INVOICE_NO_LABEL

_INVOICE_NUMBER = re.compile(r"\d{4}CC\d+", re.IGNORECASE)
_CARD_LINE = re.compile(r"\d+X+\d+", re.IGNORECASE)
_AMOUNT_ONLY = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")


def _is_label_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped.endswith(":")


def _stacked_labels(lines: list[str]) -> tuple[int, list[str]] | None:
    start: int | None = None
    labels: list[str] = []
    for index, line in enumerate(lines):
        if start is None:
            if INVOICE_NO_LABEL in line:
                start = index
                labels.append(line.strip())
            continue
        if _is_label_line(line):
            labels.append(line.strip())
            continue
        break
    if start is None or not labels:
        return None
    return start, labels


def _value_block_start(lines: list[str], after: int) -> int | None:
    for index in range(after, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if _INVOICE_NUMBER.search(stripped):
            return index
        if _CARD_LINE.search(stripped):
            return index
        if parse_date_string(stripped) is not None:
            return index
        if _AMOUNT_ONLY.match(stripped):
            return index
    return None


def _label_index(labels: list[str], target: str) -> int | None:
    target_re = label_regex(target)
    for index, line in enumerate(labels):
        if target_re.search(line):
            return index
    return None


def stacked_label_amount(text: str, label: str) -> str | None:
    """Return the amount aligned with a stacked ``label :`` row in v2 PDFs."""
    lines = text.split("\n")
    block = _stacked_labels(lines)
    if block is None:
        return None
    start, labels = block
    label_end = start + len(labels)
    value_start = _value_block_start(lines, label_end)
    if value_start is None:
        return None
    index = _label_index(labels, label)
    if index is None:
        return None
    value_index = value_start + index
    if value_index >= len(lines):
        return None
    return first_amount_in_text(lines[value_index])
