"""HDFC Swiggy credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler
from networthcsv.utils.banks.hdfc.layouts import approximate_period_if_needed
from networthcsv.utils.banks.hdfc.swiggy_layouts import (
    detect_swiggy_layout,
    get_swiggy_layout,
)
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin


@register("hdfc", "swiggy")
class HdfcSwiggyHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Swiggy HDFC Bank Credit Card Statement"]

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        if self.is_annual_statement(text):
            period = self.get_annual_period(text)
            if period is not None:
                return period
        # Always approximate missing start for Swiggy (v1 and v2).
        period_start, period_end = ContextRangePeriodMixin.get_statement_period(
            self, text
        )
        return approximate_period_if_needed(period_start, period_end)

    def get_opening_balance(self, text: str) -> str | None:
        return get_swiggy_layout(text).get_opening_balance(text)

    def get_closing_balance(self, text: str) -> str | None:
        return get_swiggy_layout(text).get_closing_balance(text)

    def hdfc_layout_id(self, text: str) -> str:
        return detect_swiggy_layout(text)

    def swiggy_layout_id(self, text: str) -> str:
        return detect_swiggy_layout(text)
