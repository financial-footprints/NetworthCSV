"""YES default credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.dates import (
    first_not_none_date,
    label_single_date_end,
)
from networthcsv.utils.banks.helpers.tables import label_next_line_amount
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin


@register("yes", "default")
class YesDefaultHandler(ContextRangePeriodMixin, CreditCardHandler):
    def period_context(self) -> str:
        return "Statement Period"

    def period_joiner(self) -> str:
        return " To "

    def mail_subjects(self) -> list[str]:
        return ["Your YES_BANK"]

    def trim_end(self) -> list[str]:
        return ["------------------End of the Statement------------------"]

    def drop_sections(self) -> list[str]:
        return [
            "Your Reward Points Summary",
            "To redeem your Reward Points",
            "Important information :",
            "Presenting EMI facility through e-Statements",
            "SMS  Help  space",
            "Important Safety Instructions",
            "Dear Cardmember,",
        ]

    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Statement Date :"),
            super().get_statement_date(text),
        )

    def get_opening_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Previous Balance :")

    def get_closing_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Total Amount Due:")
