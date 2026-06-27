"""Extract opening and closing balances from credit card statement text."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from networthcsv.pipeline.cleanup.statement_date import (
    _find_label,
    _label_regex,
)
from networthcsv.settings import (
    BalanceMarker,
    EdgeSummaryMarker,
    EquationFirstAfterMarker,
    LabelNextLineMarker,
    LabelSingleMarker,
    SingleAmountAfterMarker,
    SummaryTableColumnMarker,
    SummaryTableRowMarker,
)

_AMOUNT_TOKEN = re.compile(
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

_CURRENCY_AMOUNT_TOKEN = re.compile(
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

_CID_PATTERN = re.compile(r"\(cid:\d+\)", re.IGNORECASE)

_RS_AMOUNT = re.compile(
    r"Rs\.?\s*(-?\d[\d,]*(?:\.\d+)?|\.\d+)",
    re.IGNORECASE,
)

_DATE_IN_LINE = re.compile(
    r"\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Z]{3}\s+\d{4}",
    re.IGNORECASE,
)

_TABLE_SECTION_BOUNDARY = re.compile(
    r"Bonus/Reward|Transaction Details|Reward Summary",
    re.IGNORECASE,
)


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


def _is_inside_cid(text: str, index: int) -> bool:
    for match in _CID_PATTERN.finditer(text):
        if match.start() <= index < match.end():
            return True
    return False


def _first_amount_in_text(text: str) -> str | None:
    for match in _AMOUNT_TOKEN.finditer(text):
        if _is_inside_cid(text, match.start()):
            continue
        parsed = parse_amount_string(match.group(0))
        if parsed is not None:
            return parsed
    return None


def _amounts_with_positions(
    line: str,
    *,
    currency_only: bool = False,
) -> list[tuple[str, int]]:
    pattern = _CURRENCY_AMOUNT_TOKEN if currency_only else _AMOUNT_TOKEN
    found: list[tuple[str, int]] = []
    for match in pattern.finditer(line):
        if _is_inside_cid(line, match.start()):
            continue
        parsed = parse_amount_string(match.group(0))
        if parsed is not None:
            found.append((parsed, match.start()))
    return found


def _is_table_section_boundary(line: str) -> bool:
    return _TABLE_SECTION_BOUNDARY.search(line) is not None


def _label_position_in_headers(header_lines: list[str], column: str) -> int | None:
    for line in header_lines:
        match = _label_regex(column).search(line)
        if match is not None:
            return match.start()

    words = column.split()
    if not words:
        return None
    for word in (words[0], words[-1]) if len(words) > 1 else words:
        for line in header_lines:
            match = _label_regex(word).search(line)
            if match is not None:
                return match.start()
    return None


def _summary_row_amounts(line: str) -> tuple[list[tuple[str, int]], bool]:
    currency_amounts = _amounts_with_positions(line, currency_only=True)
    if len(currency_amounts) >= 2:
        return currency_amounts, True
    all_amounts = _amounts_with_positions(line, currency_only=False)
    if len(all_amounts) >= 2:
        return all_amounts, False
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

    amounts = _amounts_with_positions(data_line, currency_only=currency_only)
    if not amounts:
        return None
    if len(amounts) == 1:
        return 0

    return min(
        range(len(amounts)),
        key=lambda index: abs(amounts[index][1] - label_pos),
    )


def _apply_label_single(text: str, marker: LabelSingleMarker) -> str | None:
    match = _find_label(text, marker.label)
    if match is None:
        return None
    window_end = min(len(text), match.end() + 400)
    return _first_amount_in_text(text[match.end() : window_end])


def _apply_label_next_line(text: str, marker: LabelNextLineMarker) -> str | None:
    match = _find_label(text, marker.label)
    if match is None:
        return None
    window = text[match.end() : match.end() + 400]
    return _first_amount_in_text(window)


def _apply_summary_table_column(
    text: str,
    marker: SummaryTableColumnMarker,
) -> str | None:
    ctx_match = _label_regex(marker.context).search(text)
    if ctx_match is None:
        return None
    window = text[ctx_match.start() : ctx_match.start() + marker.search_chars]
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
        row_amounts, row_currency_only = _summary_row_amounts(line)
        if len(row_amounts) >= 2:
            data_line = line
            data_currency_only = row_currency_only
            break
        header_lines.append(line)

    if data_line is None or not header_lines:
        return None

    col_index = _column_index_for_label(
        header_lines,
        data_line,
        marker.column,
        currency_only=data_currency_only,
    )
    if col_index is None:
        return None
    amounts = _amounts_with_positions(data_line, currency_only=data_currency_only)
    if col_index >= len(amounts):
        return None
    return amounts[col_index][0]


def _apply_edge_summary(text: str, marker: EdgeSummaryMarker) -> str | None:
    if marker.field == "closing":
        match = _RS_AMOUNT.search(text[:3000])
        if match is None:
            return None
        return parse_amount_string(match.group(0))

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


def _apply_single_amount_after(
    text: str,
    marker: SingleAmountAfterMarker,
) -> str | None:
    match = _find_label(text, marker.anchor)
    if match is None:
        return None
    window = text[match.end() : match.end() + 500]
    for line in window.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        amounts = _amounts_with_positions(line)
        if len(amounts) == 1:
            return amounts[0][0]
    return None


def _apply_equation_first_after(
    text: str,
    marker: EquationFirstAfterMarker,
) -> str | None:
    match = _find_label(text, marker.anchor)
    if match is None:
        return None
    window = text[match.end() : match.end() + 600]
    for line in window.split("\n"):
        if "=" not in line:
            continue
        amounts = _amounts_with_positions(line)
        if amounts:
            return amounts[0][0]
    return None


def _apply_summary_table_row(
    text: str,
    marker: SummaryTableRowMarker,
) -> str | None:
    anchor = _find_label(text, marker.after)
    if anchor is None:
        return None
    tail = text[anchor.end() : anchor.end() + 1200]
    for line in tail.split("\n"):
        amounts = _amounts_with_positions(line, currency_only=True)
        if len(amounts) < 3:
            continue
        if marker.column == "opening":
            return amounts[0][0]
        return amounts[-1][0]
    return None


def _apply_marker(text: str, marker: BalanceMarker) -> str | None:
    if isinstance(marker, LabelSingleMarker):
        return _apply_label_single(text, marker)
    if isinstance(marker, LabelNextLineMarker):
        return _apply_label_next_line(text, marker)
    if isinstance(marker, SummaryTableColumnMarker):
        return _apply_summary_table_column(text, marker)
    if isinstance(marker, EdgeSummaryMarker):
        return _apply_edge_summary(text, marker)
    if isinstance(marker, SummaryTableRowMarker):
        return _apply_summary_table_row(text, marker)
    if isinstance(marker, SingleAmountAfterMarker):
        return _apply_single_amount_after(text, marker)
    if isinstance(marker, EquationFirstAfterMarker):
        return _apply_equation_first_after(text, marker)
    return None


def extract_balance(
    text: str,
    markers: tuple[BalanceMarker, ...],
) -> str | None:
    for marker in markers:
        parsed = _apply_marker(text, marker)
        if parsed is not None:
            return parsed
    return None


def extract_opening_balance(
    text: str,
    markers: tuple[BalanceMarker, ...],
) -> str | None:
    return extract_balance(text, markers)


def extract_closing_balance(
    text: str,
    markers: tuple[BalanceMarker, ...],
) -> str | None:
    return extract_balance(text, markers)
