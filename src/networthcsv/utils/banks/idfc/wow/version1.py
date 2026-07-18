"""IDFC WOW statement PDF layout v1 (classic STATEMENT SUMMARY table)."""

from __future__ import annotations

from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.tables import (
    equation_first_after,
    label_single_amount,
)
from networthcsv.utils.banks.idfc.summary import (
    classic_closing,
    classic_opening,
    inline_equation_amount,
    scrambled_classic_closing,
    scrambled_classic_opening,
)


class LayoutV1:
    def get_opening_balance(self, text: str) -> str | None:
        return first_not_none(
            classic_opening(text),
            scrambled_classic_opening(text),
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            scrambled_classic_closing(text),
            classic_closing(text),
            label_single_amount(text, "Total Amount Due"),
            equation_first_after(text, "Total Amount Due"),
            inline_equation_amount(text, "Total Amount Due"),
        )
