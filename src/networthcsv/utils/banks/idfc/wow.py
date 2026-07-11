"""IDFC WOW credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.idfc.default import IdfcDefaultHandler
from networthcsv.utils.banks.helpers.dates import (
    first_not_none_date,
    label_single_date_end,
    top_range_end,
)


@register("idfc", "wow")
class IdfcWowHandler(IdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["FIRST WOW! Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return ["IMPORTANT INFORMATION"]

    def drop_sections(self) -> list[str]:
        return [
            "Payment Modes",
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
