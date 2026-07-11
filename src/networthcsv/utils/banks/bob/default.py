"""BOB default credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.tables import (
    summary_table_column,
    summary_table_row,
)
from networthcsv.utils.banks.mixins.dates import BobDateMixin


@register("bob", "default")
class BobDefaultHandler(BobDateMixin, CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return [
            "E-statement for your BOB",
            "E-statement for your BOBCARD",
            "Duplicate Statement from BOB Card",
        ]

    def trim_end(self) -> list[str]:
        return ["Reward Summary at Card Level", "Page 1 of"]

    def get_opening_balance(self, text: str) -> str | None:
        return first_not_none(
            summary_table_column(
                text, context="Account Summary", column="Opening Balance"
            ),
            summary_table_column(
                text,
                context="This Month's Statement At A Glance",
                column="Opening Balance",
            ),
            summary_table_row(text, after="GST No:", which=2, column="opening"),
            summary_table_row(text, after="GST No:", which=1, column="opening"),
        )

    def get_closing_balance(self, text: str) -> str | None:
        return first_not_none(
            summary_table_column(
                text, context="Account Summary", column="Closing Balance"
            ),
            summary_table_column(
                text,
                context="This Month's Statement At A Glance",
                column="Closing Balance",
            ),
            summary_table_row(text, after="GST No:", which=2, column="closing"),
            summary_table_row(text, after="GST No:", which=1, column="closing"),
        )
