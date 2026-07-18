"""Federal/CSB Edge PDF text enrichment: amount color → Cr/Dr and summary labels."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_RS_AMOUNT = re.compile(
    r"Rs\.?\s*(-?\d[\d,]*(?:\.\d+)?|\.\d+)",
    re.IGNORECASE,
)

# Edge txn lines: "04 Jan 2021 DESC … Rs. 180.00" or "24 Mar 21 DESC … Rs. 612.40"
_TXN_LINE = re.compile(
    r"^\s*\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}\b",
)

_OPENING_SUMMARY_LINE = re.compile(
    r"^(\s*)((?:\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+)?"
    r"(Rs\.?\s*-?\d[\d,]*(?:\.\d+)?|\.\d+)\s*$",
    re.IGNORECASE,
)

_AMOUNT_ONLY_LINE = re.compile(
    r"^(\s*)(Rs\.?\s*-?\d[\d,]*(?:\.\d+)?|\.\d+)\s*$",
    re.IGNORECASE,
)

# Edge statement summary column (visual order, top → bottom).
# Amount patterns on Federal/CSB Edge PDFs: opening, spends, cash advances,
# fees, interest, repayments, points, total due.
EDGE_SUMMARY_LABELS: tuple[str, ...] = (
    "Opening Balance",
    "Spends",
    "Cash Advances",
    "Fees & Charges",
    "Interest Charges",
    "Repayments & Refunds",
    "Paid via points",
    "Total Amount Due",
)


def uses_edge_color_extract(bank: str, variant: str | None) -> bool:
    return variant == "edge" and bank in ("federal", "csb")


def _as_rgb(color: object) -> tuple[float, float, float] | None:
    if color is None:
        return None
    if isinstance(color, (int, float)):
        value = float(color)
        return (value, value, value)
    if not isinstance(color, (tuple, list)):
        return None
    if len(color) == 1:
        value = float(color[0])
        return (value, value, value)
    if len(color) == 3:
        return (float(color[0]), float(color[1]), float(color[2]))
    if len(color) == 4:
        # CMYK → rough RGB
        c, m, y, k = (
            float(color[0]),
            float(color[1]),
            float(color[2]),
            float(color[3]),
        )
        r = 1.0 - min(1.0, c + k)
        g = 1.0 - min(1.0, m + k)
        b = 1.0 - min(1.0, y + k)
        return (r, g, b)
    return None


def is_green_amount_color(color: object) -> bool:
    """Return True when fill color is a green shade (Edge credit amounts)."""
    rgb = _as_rgb(color)
    if rgb is None:
        return False
    red, green, blue = rgb
    # Credits are clearly green: G dominates R and B.
    return green >= 0.25 and green > red + 0.08 and green > blue + 0.08


def _char_sort_key(char: Mapping[str, Any]) -> tuple[float, float]:
    return (round(float(char.get("top", 0.0)), 1), float(char.get("x0", 0.0)))


def _cluster_amount_colors(chars: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Return is_credit flags for each Rs-amount run in reading order."""
    if not chars:
        return []

    ordered = sorted(chars, key=_char_sort_key)
    # Bucket glyphs into visual lines.
    lines: list[list[Mapping[str, Any]]] = []
    for char in ordered:
        text = str(char.get("text", ""))
        if not text or text.isspace():
            continue
        if not lines:
            lines.append([char])
            continue
        prev_top = float(lines[-1][0].get("top", 0.0))
        if abs(float(char.get("top", 0.0)) - prev_top) < 2.0:
            lines[-1].append(char)
        else:
            lines.append([char])

    runs: list[bool] = []
    for line_chars in lines:
        line_chars = sorted(line_chars, key=lambda item: float(item.get("x0", 0.0)))
        pieces: list[str] = []
        owners: list[Mapping[str, Any]] = []
        for item in line_chars:
            fragment = str(item.get("text", ""))
            pieces.append(fragment)
            owners.extend([item] * len(fragment))
        text = "".join(pieces)
        for match in _RS_AMOUNT.finditer(text):
            covering = owners[match.start() : match.end()]
            if not covering:
                covering = line_chars
            colors = [item.get("non_stroking_color") for item in covering]
            runs.append(any(is_green_amount_color(color) for color in colors))
    return runs


def _line_is_transaction(line: str) -> bool:
    return _TXN_LINE.match(line) is not None


def annotate_edge_amount_directions(
    layout_text: str,
    *,
    amount_is_credit: Sequence[bool],
) -> str:
    """Append Cr/Dr to transaction-line Rs amounts using color flags in reading order."""
    if not layout_text or not amount_is_credit:
        return layout_text

    credit_flags = list(amount_is_credit)
    flag_index = 0
    lines_out: list[str] = []

    for line in layout_text.split("\n"):
        if not _line_is_transaction(line):
            # Still consume flags for non-txn amounts so order stays aligned.
            for _ in _RS_AMOUNT.finditer(line):
                if flag_index < len(credit_flags):
                    flag_index += 1
            lines_out.append(line)
            continue

        pieces: list[str] = []
        last = 0
        for match in _RS_AMOUNT.finditer(line):
            pieces.append(line[last : match.end()])
            is_credit = False
            if flag_index < len(credit_flags):
                is_credit = credit_flags[flag_index]
                flag_index += 1
            marker = " Cr" if is_credit else " Dr"
            # Avoid double-annotating if a prior pass already added markers.
            tail = line[match.end() : match.end() + 4]
            if not re.match(r"\s*(Cr|Dr)\b", tail, re.IGNORECASE):
                pieces.append(marker)
            last = match.end()
        pieces.append(line[last:])
        lines_out.append("".join(pieces))

    return "\n".join(lines_out)


def annotate_page_text_from_chars(
    layout_text: str,
    chars: Sequence[Mapping[str, Any]],
) -> str:
    return annotate_edge_amount_directions(
        layout_text,
        amount_is_credit=_cluster_amount_colors(chars),
    )


def inject_edge_summary_labels(text: str) -> str:
    """Prepend fixed Edge summary labels to the unlabeled Rs amount column."""
    if not text.strip():
        return text
    # Already labeled — leave alone.
    if "Opening Balance" in text and "Total Amount Due" in text:
        return text

    lines = text.split("\n")
    start_idx: int | None = None
    for index, line in enumerate(lines):
        if _OPENING_SUMMARY_LINE.match(line) and _RS_AMOUNT.search(line):
            # Prefer the opening row that includes a date before Rs.
            if re.search(
                r"\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4}",
                line,
                re.IGNORECASE,
            ):
                date_match = re.search(
                    r"\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4}",
                    line,
                    re.IGNORECASE,
                )
                amount_match = _RS_AMOUNT.search(line)
                if (
                    date_match is not None
                    and amount_match is not None
                    and date_match.start() < amount_match.start()
                ):
                    start_idx = index
                    break

    if start_idx is None:
        return text

    collected: list[tuple[int, str, re.Match[str]]] = []
    index = start_idx
    while index < len(lines) and len(collected) < len(EDGE_SUMMARY_LABELS):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _AMOUNT_ONLY_LINE.match(line) or _OPENING_SUMMARY_LINE.match(line)
        if match is None or _RS_AMOUNT.search(line) is None:
            break
        amount_match = _RS_AMOUNT.search(line)
        assert amount_match is not None
        collected.append((index, line, amount_match))
        index += 1

    if len(collected) != len(EDGE_SUMMARY_LABELS):
        return text

    for label_index, (line_index, line, amount_match) in enumerate(collected):
        label = EDGE_SUMMARY_LABELS[label_index]
        indent = re.match(r"^\s*", line)
        prefix = indent.group(0) if indent else ""
        before_amount = line[: amount_match.start()].rstrip()
        amount_and_rest = line[amount_match.start() :]
        if before_amount.strip():
            # Keep opening date (or other left text) after the label.
            left = before_amount[len(prefix) :].strip()
            lines[line_index] = f"{prefix}{label}  {left}  {amount_and_rest.lstrip()}"
        else:
            lines[line_index] = f"{prefix}{label}  {amount_and_rest.lstrip()}"

    return "\n".join(lines)
