"""IDFC WOW statement PDF layout v2 (modern inline summary header)."""

from __future__ import annotations

from networthcsv.utils.banks.helpers.amounts import (
    first_amount_in_text,
    first_not_none,
)
from networthcsv.utils.banks.helpers.dates import label_regex
from networthcsv.utils.banks.helpers.tables import (
    equation_first_after,
    label_single_amount,
)
from networthcsv.utils.banks.idfc.summary import inline_equation_amount
from networthcsv.utils.banks.idfc.wow.common import is_standalone_opening_balance_line


def _rewards_sidecar_opening(text: str) -> str | None:
    """Opening amount on the line above a standalone Opening Balance label."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not is_standalone_opening_balance_line(line):
            continue
        for prev_index in range(index - 1, -1, -1):
            previous = lines[prev_index].strip()
            if not previous:
                continue
            if label_regex("Rewards Summary").search(
                previous
            ) or previous.lower().startswith("r"):
                amount = first_amount_in_text(lines[prev_index])
                if amount is not None:
                    return amount
            break
    return None


class LayoutV2:
    def get_opening_balance(self, text: str) -> str | None:
        return first_not_none(
            _rewards_sidecar_opening(text),
            inline_equation_amount(text, "Opening Balance"),
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            equation_first_after(text, "Total Amount Due"),
            label_single_amount(text, "Total Amount Due"),
            inline_equation_amount(text, "Total Amount Due"),
        )
