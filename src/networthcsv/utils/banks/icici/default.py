"""ICICI default credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.dates import (
    date_after_label,
    label_range_end,
    label_range_period,
)
from networthcsv.utils.banks.helpers.tables import (
    label_next_line_amount,
    summary_table_column,
)

_ICICI_DROP_SECTIONS = [
    "For exclusive",
    "offers, visit",
    "IMPORTANT MESSAGES",
    "Download the iMobile Pay app",
    "CREDIT CARD STATEMENT",
    "GREAT    OFFERS    ON   YOUR   CARD",
    "IMPORTANT     INFORMATION      ON  YOUR   CREDIT   CARD",
    "ICICl Bank Rewards",
]


@register("icici", "default")
@register("icici", "coral")
@register("icici", "platinum")
class IciciDefaultHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return ["ICICI Bank Credit Card Statement for the period"]

    def trim_end(self) -> list[str]:
        return ["MOST IMPORTANT TERMS AND CONDITIONS (MITC)"]

    def drop_sections(self) -> list[str]:
        return list(_ICICI_DROP_SECTIONS)

    def get_statement_date(self, text: str) -> date | None:
        parsed = date_after_label(text, "STATEMENT DATE")
        if parsed is not None:
            return parsed
        return label_range_end(text, "Statement period :", " to ")

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = label_range_period(
            text, "Statement period :", " to "
        )
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None

    def get_opening_balance(self, text: str) -> str | None:
        return summary_table_column(
            text,
            context="Previous Balance",
            column="Previous Balance",
            search_chars=300,
        )

    def get_closing_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Total Amount due")
