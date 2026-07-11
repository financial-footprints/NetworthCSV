"""IDFC default credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.tables import (
    label_single_amount,
    summary_table_column,
)


@register("idfc", "default")
class IdfcDefaultHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return ["Credit Card Statement"]

    def get_statement_date(self, text: str) -> date | None:
        return None

    def get_opening_balance(self, text: str) -> str | None:
        return summary_table_column(
            text,
            context="STATEMENT SUMMARY",
            column="Opening Balance",
        )

    def get_closing_balance(self, text: str) -> str | None:
        return label_single_amount(text, "Total Amount Due")
