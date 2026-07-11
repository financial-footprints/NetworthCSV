"""HDFC default credit card handler."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.dates import (
    first_not_none_date,
    label_single_date_end,
)
from networthcsv.utils.banks.helpers.tables import (
    summary_table_column,
    summary_table_row,
)
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin

_HDFC_DROP_SECTIONS = [
    "Benefits on your card",
    "IMPORTANT INFORMATION",
    "Your Card Control Setting",
    "Purchase Indicator / Insights",
    "Offers on your card",
    "Important Information",
    "Useful Links",
    "To update your personal details, please write a letter to",
]


@register("hdfc", "default")
class HdfcDefaultHandler(ContextRangePeriodMixin, CreditCardHandler):
    def period_context(self) -> str:
        return "Billing Period"

    def period_joiner(self) -> str:
        return " - "

    def mail_subjects(self) -> list[str]:
        return ["HDFC Bank Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return ["Reward Points Summary"]

    def drop_sections(self) -> list[str]:
        return list(_HDFC_DROP_SECTIONS)

    def balance_match_tolerance(self) -> Decimal:
        return Decimal("0.99")

    def period_start_day(self) -> int | None:
        return 21

    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Statement Date"),
            super().get_statement_date(text),
        )

    def get_opening_balance(self, text: str) -> str | None:
        return first_not_none(
            summary_table_column(
                text, context="Account Summary", column="Opening Balance"
            ),
            summary_table_row(text, after="Account Summary", which=1, column="opening"),
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            summary_table_column(text, context="Account Summary", column="Total Dues"),
            summary_table_row(text, after="Account Summary", which=1, column="closing"),
        )
