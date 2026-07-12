"""IDFC credit card statement summary balance extraction."""

from __future__ import annotations

import re

from networthcsv.utils.banks.helpers.amounts import (
    _AMOUNT_TOKEN,
    first_amount_in_text,
    first_not_none,
)
from networthcsv.utils.banks.helpers.dates import find_label, label_regex
from networthcsv.utils.banks.helpers.tables import (
    _column_index_for_label,
    _is_table_section_boundary,
    _summary_row_amounts,
    _summary_table_header_seen,
    amounts_with_positions,
    equation_first_after,
    label_single_amount,
)

_STACKED_BOUNDARY = re.compile(
    r"Minimum Amount Due|^\+$|^-$|^=$",
    re.IGNORECASE,
)

_DATE_ONLY_LINE = re.compile(
    r"^\d{1,2}/(?:\d{1,2}|[A-Za-z]{3})/\d{2,4}$",
    re.IGNORECASE,
)

_DATE_OR_RANGE_LINE = re.compile(
    r"^\d{1,2}/(?:\d{1,2}|[A-Za-z]{3})/\d{2,4}"
    r"(?:\s+-\s+\d{1,2}/(?:\d{1,2}|[A-Za-z]{3})/\d{2,4})?$",
    re.IGNORECASE,
)

_ORPHAN_CR_DR = re.compile(r"^(?:CR|DR)$", re.IGNORECASE)
_CR_DR_MARKER = re.compile(r"\b(CR|DR)\b", re.IGNORECASE)
_MAX_MARKER_DISTANCE = 80


def _is_summary_date_line(line: str) -> bool:
    stripped = line.strip()
    return bool(_DATE_ONLY_LINE.match(stripped) or _DATE_OR_RANGE_LINE.match(stripped))


def _r_prefixed_amount_count(line: str) -> int:
    return sum(
        1
        for match in _AMOUNT_TOKEN.finditer(line)
        if match.group(0).lstrip().lower().startswith("r")
    )


def join_orphan_cr_dr(text: str) -> str:
    """Join exclusive CR/DR suffix lines onto the previous amount line."""
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _ORPHAN_CR_DR.match(stripped) and result:
            while result and not result[-1].strip():
                result.pop()
            if result:
                result[-1] = f"{result[-1].rstrip()} {stripped}"
            continue
        result.append(line)
    return "\n".join(result)


def _is_cr_dr_suffix_line(line: str) -> bool:
    return _CR_DR_MARKER.search(line) is not None and first_amount_in_text(line) is None


def _merge_row_with_cr_dr_suffix(data_line: str, suffix_line: str) -> str:
    markers = sorted(
        (match.start(), match.group(1).upper())
        for match in _CR_DR_MARKER.finditer(suffix_line)
    )
    if not markers:
        return data_line

    amount_matches = list(_AMOUNT_TOKEN.finditer(data_line))
    if not amount_matches:
        return data_line

    amounts = [(match.start(), match) for match in amount_matches]
    paired: dict[int, str] = {}
    used_amounts: set[int] = set()

    for marker_pos, marker_label in markers:
        best_index: int | None = None
        best_distance = _MAX_MARKER_DISTANCE + 1
        for index, (amount_pos, _) in enumerate(amounts):
            if index in used_amounts:
                continue
            distance = abs(marker_pos - amount_pos)
            if distance <= _MAX_MARKER_DISTANCE and distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index is not None:
            used_amounts.add(best_index)
            paired[best_index] = marker_label

    parts: list[str] = []
    last_end = 0
    for index, match in enumerate(amount_matches):
        parts.append(data_line[last_end : match.start()])
        suffix = f" {paired[index]}" if index in paired else ""
        parts.append(match.group(0).rstrip() + suffix)
        last_end = match.end()
    parts.append(data_line[last_end:])
    return "".join(parts)


def _join_detached_cr_dr_suffix(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            index + 1 < len(lines)
            and _is_cr_dr_suffix_line(lines[index + 1])
            and len(amounts_with_positions(line)) >= 2
        ):
            result.append(_merge_row_with_cr_dr_suffix(line, lines[index + 1]))
            index += 2
            continue
        result.append(line)
        index += 1
    return "\n".join(result)


def normalize_cr_dr_layout(text: str) -> str:
    """Normalize IDFC summary amounts with split or detached CR/DR markers."""
    return _join_detached_cr_dr_suffix(join_orphan_cr_dr(text))


def _header_block_window(text: str) -> str:
    txn_match = label_regex("YOUR TRANSACTIONS").search(text)
    end = txn_match.start() if txn_match is not None else min(len(text), 3000)
    window = text[:end]
    summary_match = label_regex("STATEMENT SUMMARY").search(window)
    if summary_match is not None:
        before_summary = window[: summary_match.start()]
        if _summary_table_header_seen(before_summary.split("\n")):
            return before_summary
    return window


def _equation_total_in_window(window: str) -> str | None:
    lines = window.split("\n")
    for index, line in enumerate(lines):
        if line.strip() not in ("-", "="):
            continue
        for next_line in lines[index + 1 : index + 3]:
            parsed = first_amount_in_text(next_line)
            if parsed is not None:
                return parsed
    return None


def _parse_header_block_data(
    window: str,
) -> tuple[list[str], list[str]] | None:
    header_lines: list[str] = []
    data_parts: list[str] = []
    collecting_data = False

    for line in window.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_table_section_boundary(line):
            break
        if label_regex("STATEMENT SUMMARY").search(stripped):
            break
        if _is_summary_date_line(stripped):
            continue

        row_amounts, _ = _summary_row_amounts(line)
        if not collecting_data:
            if (
                row_amounts
                and len(row_amounts) >= 3
                and _summary_table_header_seen(header_lines)
            ):
                collecting_data = True
                data_parts.append(line)
                continue
            if not row_amounts:
                header_lines.append(line)
            continue
        if row_amounts:
            data_parts.append(line)
            continue
        break

    if not header_lines or not data_parts:
        return None
    return header_lines, data_parts


def _split_row_column(data_parts: list[str], column: str) -> str | None:
    if column == "Opening Balance" and len(data_parts) >= 2:
        amounts, _ = _summary_row_amounts(data_parts[-1])
        if len(amounts) >= 3:
            return amounts[2][0]
    if column == "Total Amount Due" and data_parts:
        amounts, _ = _summary_row_amounts(data_parts[0])
        if len(amounts) >= 3:
            return amounts[2][0]
    return None


def header_block_summary_column(text: str, *, column: str) -> str | None:
    """Extract a summary column from scrambled pre-STATEMENT SUMMARY header blocks."""
    window = normalize_cr_dr_layout(_header_block_window(text))
    parsed = _parse_header_block_data(window)
    if parsed is None:
        return None

    header_lines, data_parts = parsed
    split_value = _split_row_column(data_parts, column)
    if split_value is not None:
        return split_value

    data_line = " ".join(data_parts)
    _, data_currency_only = _summary_row_amounts(data_line)
    col_index = _column_index_for_label(
        header_lines,
        data_line,
        column,
        currency_only=data_currency_only,
    )
    if col_index is not None:
        amounts = amounts_with_positions(data_line, currency_only=data_currency_only)
        if col_index < len(amounts):
            return amounts[col_index][0]

    if column == "Total Amount Due":
        return _equation_total_in_window(window)
    return None


def scrambled_classic_opening(text: str) -> str | None:
    return header_block_summary_column(text, column="Opening Balance")


def scrambled_classic_closing(text: str) -> str | None:
    return header_block_summary_column(text, column="Total Amount Due")


def _idfc_classic_summary_amounts(text: str) -> list[tuple[str, int]] | None:
    """Return currency amounts from the IDFC classic STATEMENT SUMMARY data row."""
    ctx_match = label_regex("STATEMENT SUMMARY").search(text)
    if ctx_match is None:
        return None

    header_lines: list[str] = []
    for line in text[ctx_match.start() : ctx_match.start() + 2000].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_table_section_boundary(line):
            break
        if _is_summary_date_line(stripped):
            continue
        row_amounts, currency_only = _summary_row_amounts(line)
        if _r_prefixed_amount_count(line) >= 4 and _summary_table_header_seen(
            header_lines
        ):
            amounts = amounts_with_positions(line, currency_only=currency_only)
            if len(amounts) >= 4:
                return amounts
        if not row_amounts or len(row_amounts) < 3:
            header_lines.append(line)
    return None


def classic_opening(text: str) -> str | None:
    amounts = _idfc_classic_summary_amounts(text)
    if amounts is not None and len(amounts) >= 2:
        return amounts[1][0]
    return None


def inline_equation_amount(text: str, label: str) -> str | None:
    match = find_label(text, label)
    if match is None:
        return None
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    return first_amount_in_text(line)


def _stacked_summary_window(text: str) -> str | None:
    anchor = find_label(text, "Statement Summary")
    if anchor is None:
        return None
    tail = text[anchor.start() : anchor.start() + 2500]
    lines = tail.split("\n")
    collected: list[str] = []
    for line in lines:
        if _STACKED_BOUNDARY.search(line.strip()):
            break
        collected.append(line)
    return "\n".join(collected)


def _stacked_amount_lines(window: str) -> list[str]:
    window = normalize_cr_dr_layout(window)
    amounts: list[str] = []
    for line in window.split("\n"):
        stripped = line.strip()
        if not stripped or _is_summary_date_line(stripped):
            continue
        if label_regex("Statement Summary").search(stripped):
            continue
        if label_regex("Opening Balance").fullmatch(stripped):
            continue
        if label_regex("Total Amount Due").fullmatch(stripped):
            continue
        if label_regex("Purchases").fullmatch(stripped):
            continue
        if label_regex("Payments & Refunds").fullmatch(stripped):
            continue
        if label_regex("EMI & Other Debits").fullmatch(stripped):
            continue
        if label_regex("Payment Due Date").fullmatch(stripped):
            continue
        parsed = first_amount_in_text(line)
        if parsed is not None and stripped.lower().startswith("r"):
            amounts.append(parsed)
        elif parsed is not None and re.search(
            r"[\d,]+\.\d{2}\s*(?:CR|DR)?", stripped, re.I
        ):
            amounts.append(parsed)
    return amounts


def stacked_equation_amount(text: str, label: str) -> str | None:
    window = _stacked_summary_window(text)
    if window is None:
        return None

    label_match = find_label(window, label)
    if label_match is None:
        return None

    tail = window[label_match.end() :]
    amounts: list[str] = []
    for line in tail.split("\n"):
        stripped = line.strip()
        if not stripped or _is_summary_date_line(stripped):
            continue
        if _STACKED_BOUNDARY.search(stripped):
            break
        if label_regex("Minimum Amount Due").search(stripped):
            break
        if re.fullmatch(r"[+\-=]", stripped):
            break
        if label_regex(label).search(stripped) and first_amount_in_text(line) is None:
            continue
        parsed = first_amount_in_text(line)
        if parsed is not None:
            amounts.append(parsed)

    if not amounts:
        return None
    if label == "Total Amount Due":
        return amounts[-1]
    for amount in amounts:
        if amount != "0.00":
            return amount
    return amounts[0]


def _stacked_opening_from_amounts(text: str) -> str | None:
    window = _stacked_summary_window(text)
    if window is None:
        return None
    amounts = _stacked_amount_lines(window)
    for amount in amounts:
        if amount != "0.00":
            return amount
    return amounts[0] if amounts else None


def _stacked_closing_from_amounts(text: str) -> str | None:
    window = _stacked_summary_window(text)
    if window is None:
        return None
    amounts = _stacked_amount_lines(window)
    return amounts[-1] if amounts else None


def idfc_opening_balance(text: str) -> str | None:
    normalized = normalize_cr_dr_layout(text)
    return first_not_none(
        classic_opening(normalized),
        inline_equation_amount(normalized, "Opening Balance"),
        stacked_equation_amount(normalized, "Opening Balance"),
        scrambled_classic_opening(normalized),
        _stacked_opening_from_amounts(normalized),
    )


def idfc_closing_balance(text: str) -> str | None:
    normalized = normalize_cr_dr_layout(text)
    return first_not_none(
        scrambled_classic_closing(normalized),
        stacked_equation_amount(normalized, "Total Amount Due"),
        label_single_amount(normalized, "Total Amount Due"),
        equation_first_after(normalized, "Total Amount Due"),
        inline_equation_amount(normalized, "Total Amount Due"),
        _stacked_closing_from_amounts(normalized),
    )
