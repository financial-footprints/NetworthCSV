"""Table and label-based balance extraction helpers."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.amounts import (
    amounts_with_positions,
    first_amount_in_text,
    parse_amount_string,
)
from networthcsv.utils.banks.helpers.dates import find_label, label_regex

_TABLE_SECTION_BOUNDARY = re.compile(
    r"Bonus/Reward|Transaction Date|Transaction Details|Reward Summary",
    re.IGNORECASE,
)

_SUMMARY_TABLE_HEADER = re.compile(
    r"Opening|Balance|Total\s+Dues|Credits|Debits|Charges|Payment|Purchase|Finance|"
    r"Previous\s+Balance|Closing\s+Balance",
    re.IGNORECASE,
)

_RS_AMOUNT = re.compile(
    r"Rs\.?\s*(-?\d[\d,]*(?:\.\d+)?|\.\d+)",
    re.IGNORECASE,
)

_DATE_IN_LINE = re.compile(
    r"\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Z]{3}\s+\d{4}",
    re.IGNORECASE,
)

_DATE_ONLY_LINE = re.compile(
    r"^\d{1,2}/(?:\d{1,2}|[A-Za-z]{3})/\d{2,4}$",
    re.IGNORECASE,
)


def _is_table_section_boundary(line: str) -> bool:
    return _TABLE_SECTION_BOUNDARY.search(line) is not None


def _summary_table_header_seen(header_lines: list[str]) -> bool:
    return any(_SUMMARY_TABLE_HEADER.search(line) for line in header_lines)


def _label_position_in_headers(header_lines: list[str], column: str) -> int | None:
    for line in header_lines:
        match = label_regex(column).search(line)
        if match is not None:
            return match.start()

    words = column.split()
    if not words:
        return None
    if len(words) > 1:
        last_pos: int | None = None
        first_pos: int | None = None
        for line in header_lines:
            match = label_regex(words[-1]).search(line)
            if match is not None:
                last_pos = match.start()
            match = label_regex(words[0]).search(line)
            if match is not None and first_pos is None:
                first_pos = match.start()
        if last_pos is not None:
            return last_pos
        if first_pos is not None:
            return first_pos
        return None

    for line in header_lines:
        match = label_regex(words[0]).search(line)
        if match is not None:
            return match.start()
    return None


def _summary_row_amounts(line: str) -> tuple[list[tuple[str, int]], bool]:
    all_amounts = amounts_with_positions(line, currency_only=False)
    if len(all_amounts) >= 3:
        return all_amounts, False
    currency_amounts = amounts_with_positions(line, currency_only=True)
    if len(currency_amounts) >= 3:
        return currency_amounts, True
    if len(all_amounts) >= 2:
        return all_amounts, False
    if len(currency_amounts) >= 2:
        return currency_amounts, True
    return [], True


def _column_index_for_label(
    header_lines: list[str],
    data_line: str,
    column: str,
    *,
    currency_only: bool = True,
) -> int | None:
    label_pos = _label_position_in_headers(header_lines, column)
    if label_pos is None:
        return None

    amounts = amounts_with_positions(data_line, currency_only=currency_only)
    if not amounts:
        return None
    if len(amounts) == 1:
        return 0

    return min(
        range(len(amounts)),
        key=lambda index: abs(amounts[index][1] - label_pos),
    )


def summary_table_column(
    text: str,
    *,
    context: str,
    column: str,
    search_chars: int = 2000,
) -> str | None:
    ctx_match = label_regex(context).search(text)
    if ctx_match is None:
        return None
    window = text[ctx_match.start() : ctx_match.start() + search_chars]
    lines = window.split("\n")

    header_lines: list[str] = []
    data_line: str | None = None
    data_currency_only = True
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_table_section_boundary(line):
            break
        if _DATE_ONLY_LINE.match(stripped):
            continue
        row_amounts, row_currency_only = _summary_row_amounts(line)
        if len(row_amounts) >= 3 and _summary_table_header_seen(header_lines):
            data_line = line
            data_currency_only = row_currency_only
            break
        header_lines.append(line)

    if data_line is None or not header_lines:
        return None

    col_index = _column_index_for_label(
        header_lines,
        data_line,
        column,
        currency_only=data_currency_only,
    )
    if col_index is None:
        return None
    amounts = amounts_with_positions(data_line, currency_only=data_currency_only)
    if col_index >= len(amounts):
        return None
    return amounts[col_index][0]


def summary_table_row(
    text: str,
    *,
    after: str,
    which: int,
    column: str,
) -> str | None:
    anchor = find_label(text, after)
    if anchor is None:
        return None
    tail = text[anchor.end() : anchor.end() + 1200]
    match_count = 0
    for line in tail.split("\n"):
        amounts = amounts_with_positions(line, currency_only=True)
        if len(amounts) < 3:
            continue
        match_count += 1
        if match_count < which:
            continue
        if column == "opening":
            return amounts[0][0]
        return amounts[-1][0]
    return None


def edge_summary_opening(text: str) -> str | None:
    for line in text[:4000].split("\n"):
        date_match = _DATE_IN_LINE.search(line)
        if date_match is None:
            continue
        amount_match = _RS_AMOUNT.search(line)
        if amount_match is None:
            continue
        if amount_match.start() < date_match.start():
            continue
        return parse_amount_string(amount_match.group(0))
    return None


def edge_summary_closing(text: str) -> str | None:
    match = _RS_AMOUNT.search(text[:3000])
    if match is None:
        return None
    return parse_amount_string(match.group(0))


def label_single_amount(text: str, label: str) -> str | None:
    match = find_label(text, label)
    if match is None:
        return None
    window_end = min(len(text), match.end() + 400)
    for line in text[match.end() : window_end].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _DATE_ONLY_LINE.match(stripped):
            continue
        parsed = first_amount_in_text(line)
        if parsed is not None:
            return parsed
    return None


def label_next_line_amount(text: str, label: str) -> str | None:
    match = find_label(text, label)
    if match is None:
        return None
    tail = text[match.end() : match.end() + 400]
    line_break = tail.find("\n")
    if line_break == -1:
        return None
    for line in tail[line_break + 1 :].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        currency_amounts = amounts_with_positions(line, currency_only=True)
        if currency_amounts:
            return currency_amounts[0][0]
        amounts = amounts_with_positions(line, currency_only=False)
        if amounts:
            return amounts[0][0]
    return None


def single_amount_after(text: str, anchor: str) -> str | None:
    match = find_label(text, anchor)
    if match is None:
        return None
    window = text[match.end() : match.end() + 500]
    for line in window.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        amounts = amounts_with_positions(line)
        if len(amounts) == 1:
            return amounts[0][0]
    return None


def equation_first_after(text: str, anchor: str) -> str | None:
    match = find_label(text, anchor)
    if match is None:
        return None
    window = text[match.end() : match.end() + 600]
    for line in window.split("\n"):
        if "=" not in line:
            continue
        amounts = amounts_with_positions(line)
        if amounts:
            return amounts[0][0]
    return None
