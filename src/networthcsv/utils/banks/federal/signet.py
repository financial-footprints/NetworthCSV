"""Federal Signet credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.dates import (
    first_not_none_date,
    label_range_end,
    label_range_period,
    label_single_date_end,
    top_range_end,
)
from networthcsv.utils.banks.helpers.tables import (
    label_next_line_amount,
    summary_table_row,
)


@register("federal", "signet")
class FederalSignetHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return ["Credit Card Statement"]

    def mail_body_contains(self) -> list[str]:
        return ["<title>Signet</title>"]

    def trim_end(self) -> list[str]:
        return ["GSTN of Federal Bank"]

    def drop_sections(self) -> list[str]:
        return [
            "The following illustration will indicate",
            "Organic Credit Cards",
            "Transaction dispute needs to be reported",
        ]

    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Statement Date"),
            label_range_end(text, "Statement Period", " to "),
            top_range_end(text, " - ", search_chars=2000),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = label_range_period(text, "Statement Period", " to ")
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None

    def get_opening_balance(self, text: str) -> str | None:
        return summary_table_row(
            text, after="Payment Due Date", which=1, column="opening"
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            label_next_line_amount(text, "Total Amount Due (in Rs.)"),
            summary_table_row(
                text, after="Payment Due Date", which=1, column="closing"
            ),
        )
