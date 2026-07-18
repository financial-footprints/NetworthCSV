"""IDFC WOW statement PDF layout v3 (stacked label/amount summary)."""

from __future__ import annotations

from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.tables import (
    equation_first_after,
    label_single_amount,
)
from networthcsv.utils.banks.idfc.summary import (
    _leading_stacked_closing,
    _leading_stacked_opening,
    _stacked_closing_from_amounts,
    _stacked_opening_from_amounts,
    inline_equation_amount,
    scrambled_classic_closing,
    scrambled_classic_opening,
    stacked_equation_amount,
)


class LayoutV3:
    def get_opening_balance(self, text: str) -> str | None:
        return first_not_none(
            _leading_stacked_opening(text),
            stacked_equation_amount(text, "Opening Balance"),
            _stacked_opening_from_amounts(text),
            scrambled_classic_opening(text),
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            _leading_stacked_closing(text),
            stacked_equation_amount(text, "Total Amount Due"),
            _stacked_closing_from_amounts(text),
            scrambled_classic_closing(text),
            label_single_amount(text, "Total Amount Due"),
            equation_first_after(text, "Total Amount Due"),
            inline_equation_amount(text, "Total Amount Due"),
        )
