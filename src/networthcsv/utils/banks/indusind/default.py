"""IndusInd default credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.dates import date_after_label
from networthcsv.utils.banks.helpers.tables import label_next_line_amount
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin


@register("indusind", "default")
@register("indusind", "auraedge")
@register("indusind", "amex-epay")
class IndusindDefaultHandler(ContextRangePeriodMixin, CreditCardHandler):
    def period_context(self) -> str:
        return "Statement Period"

    def period_joiner(self) -> str:
        return " To "

    def mail_subjects(self) -> list[str]:
        return ["IndusInd Bank Credit Card"]

    def trim_end(self) -> list[str]:
        return ["Rewards Opening Balance"]

    def drop_sections(self) -> list[str]:
        return [
            "IMPORTANT MESSAGES:",
            "PROMOTIONAL MESSAGES:",
            "MARKETING MESSAGE",
            "NOTE: *Total of points redeemed",
            "With IndusAlerts",
            "Secure your IndusInd Bank Credit Card on-the-go",
            "HOW TO MAKE PAYMENTS",
            "FEES & CHARGES",
        ]

    def get_statement_date(self, text: str) -> date | None:
        end = super().get_statement_date(text)
        if end is not None:
            return end
        return date_after_label(text, "Statement Date")

    def get_opening_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Previous Balance")

    def get_closing_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Total Amount Due")
