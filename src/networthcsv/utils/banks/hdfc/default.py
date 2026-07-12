"""HDFC default credit card handler."""

from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.dates import (
    date_after_label,
    first_not_none_date,
    label_single_date_end,
)
from networthcsv.utils.banks.helpers.tables import (
    summary_table_column,
    summary_table_row,
)
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin
from networthcsv.utils.statement_period import parse_month_year_token

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

_YEARLY_PERIOD_PATTERN = re.compile(
    r"period from\s+([A-Z]+-\d{2,4})\s+to\s+([A-Z]+-\d{2,4})",
    re.IGNORECASE,
)


@register("hdfc", "default")
class HdfcDefaultHandler(ContextRangePeriodMixin, CreditCardHandler):
    def period_context(self) -> str:
        return "Billing Period"

    def period_joiner(self) -> str:
        return " - "

    def mail_subjects(self) -> list[str]:
        return ["HDFC Bank Credit Card Statement"]

    def yearly_mail_subjects(self) -> list[str]:
        return ["Year End Statement Summary"]

    def year_display(self) -> Literal["fiscal_year", "calendar_year"]:
        return "fiscal_year"

    def trim_end(self) -> list[str]:
        return ["Reward Points Summary"]

    def drop_sections(self) -> list[str]:
        return list(_HDFC_DROP_SECTIONS)

    def balance_match_tolerance(self) -> Decimal:
        return Decimal("0.99")

    def is_yearly_statement(self, text: str) -> bool:
        lowered = text.lower()
        if (
            "year end statement" in lowered
            and "account summary for the period from" in lowered
        ):
            return True
        if _YEARLY_PERIOD_PATTERN.search(text) is None:
            return False
        return "year end statement" in lowered or "account summary" in lowered

    def get_yearly_period(self, text: str) -> tuple[date, date] | None:
        match = _YEARLY_PERIOD_PATTERN.search(text)
        if match is None:
            return None
        start_token = parse_month_year_token(match.group(1))
        end_token = parse_month_year_token(match.group(2))
        if start_token is None or end_token is None:
            return None
        start_year, start_month = start_token
        end_year, end_month = end_token
        end_day = calendar.monthrange(end_year, end_month)[1]
        return date(start_year, start_month, 1), date(end_year, end_month, end_day)

    def get_statement_date(self, text: str) -> date | None:
        if self.is_yearly_statement(text):
            period = self.get_yearly_period(text)
            if period is not None:
                return period[1]
        return first_not_none_date(
            label_single_date_end(text, "Statement Date"),
            date_after_label(text, "Statement Date"),
            date_after_label(text, "Address"),
            super().get_statement_date(text),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        if self.is_yearly_statement(text):
            period = self.get_yearly_period(text)
            if period is not None:
                return period
        return super().get_statement_period(text)

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
