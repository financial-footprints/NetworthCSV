"""PNB statement PDF layout v1 (classic, statement block near top)."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.dates import (
    context_range_end,
    context_range_period,
    date_after_label,
    first_not_none_date,
    label_single_date_end,
)
from networthcsv.utils.banks.helpers.tables import (
    label_single_amount,
    summary_table_column,
)
from networthcsv.utils.banks.pnb.default._text import prepare_statement_text
from networthcsv.utils.banks.pnb.invoice import extract_invoice_number


class LayoutV1:
    def trim_start(self) -> list[str]:
        return []

    def clean_text(self, raw: str) -> str:
        return prepare_statement_text(raw, trim_start=self.trim_start())

    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Invoice Date :"),
            date_after_label(text, "Invoice Date :"),
            context_range_end(text, "From", " to "),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = context_range_period(text, "From", " to ")
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None

    def get_opening_balance(self, text: str) -> str | None:
        return summary_table_column(
            text,
            context="Account Summary",
            column="Previous Balance",
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            summary_table_column(
                text,
                context="Account Summary",
                column="Total Amount Due for Month",
            ),
            label_single_amount(text, "Total Amount Due for Month"),
            label_single_amount(text, "Total Amount Due :"),
        )

    def get_invoice_number(self, text: str) -> str | None:
        return extract_invoice_number(text)
