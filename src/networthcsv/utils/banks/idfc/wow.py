"""IDFC WOW credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.idfc.default import IdfcDefaultHandler
from networthcsv.utils.banks.idfc.summary import (
    idfc_closing_balance,
    idfc_opening_balance,
)
from networthcsv.utils.banks.helpers.dates import (
    first_not_none_date,
    label_range_period,
    label_single_date_end,
    top_range_end,
    top_range_period,
)


@register("idfc", "wow")
class IdfcWowHandler(IdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return [
            "FIRST WOW! Credit Card Statement",
            "FIRST WOW Credit Card Statement",
            "Your Credit Card Statement",
        ]

    def trim_end(self) -> list[str]:
        return ["IMPORTANT INFORMATION"]

    def drop_sections(self) -> list[str]:
        return [
            "Payment Modes",
            "PAYMENT MODES",
            "Pay via our new Mobile App",
            "Need help Check out our FAQs",
            "Pay Now        Pay in EMI",
            "3X rewards on UPI",
            "Refer this Credit Card",
            "CHECK OUT WHY",
            "Covert your IDFC FIRST Bank Credit Card",
            "Late payment fee would be levied if Minimum",
            "SPECIAL BENEFITS ON YOUR CARD",
            "OFFER OF THE MONTH",
            "YOU MADE A GREAT CHOICE",
            "Enjoy the Convenience",
            "Your Card Information",
        ]

    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Statement Date"),
            top_range_end(text, " - ", search_chars=500),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = label_range_period(text, "Statement Date", " to ")
        if period_start is not None and period_end is not None:
            return period_start, period_end
        period_start, period_end = top_range_period(text, " - ", search_chars=500)
        if period_start is not None and period_end is not None:
            return period_start, period_end
        period_start, period_end = label_range_period(text, "Statement Period", " - ")
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None

    def get_opening_balance(self, text: str) -> str | None:
        return idfc_opening_balance(text)

    def get_closing_balance(self, text: str) -> str | None:
        return idfc_closing_balance(text)
