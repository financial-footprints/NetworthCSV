"""ICICI default credit card handler."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.dates import (
    date_after_label,
    first_not_none_date,
    label_range_end,
    label_range_period,
)
from networthcsv.utils.banks.helpers.tables import (
    label_next_line_amount,
    summary_table_column,
)

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount
    from networthcsv.utils.banks.period import PeriodSource

_ICICI_DROP_SECTIONS = [
    "For exclusive",
    "offers, visit",
    "IMPORTANT MESSAGES",
    "Download the iMobile Pay app",
    "CREDIT CARD STATEMENT",
    "GREAT    OFFERS    ON   YOUR   CARD",
    "IMPORTANT     INFORMATION      ON  YOUR   CREDIT   CARD",
    "ICICl Bank Rewards",
    "SPENDS OVERVIEW",
    "# International Spends",
    "Others-100%",
    "www.icicibank.com/offers",
    "For any query, you may write to us on customer.care",
    "T&C apply",
]

_STATEMENT_PERIOD_LABELS = (
    "Statement period :",
    "Statement Period:",
    "Statement Period",
)
_STATEMENT_PERIOD_JOINER = " to "


@register("icici", "default")
@register("icici", "coral")
@register("icici", "platinum")
class IciciDefaultHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return ["ICICI Bank Credit Card Statement for the period"]

    def year_display(self) -> Literal["fiscal_year", "calendar_year"]:
        return "fiscal_year"

    def trim_end(self) -> list[str]:
        return ["MOST IMPORTANT TERMS AND CONDITIONS (MITC)"]

    def drop_sections(self) -> list[str]:
        return list(_ICICI_DROP_SECTIONS)

    def get_statement_date(self, text: str) -> date | None:
        parsed = date_after_label(text, "STATEMENT DATE")
        if parsed is not None:
            return parsed
        return first_not_none_date(
            *(
                label_range_end(text, label, _STATEMENT_PERIOD_JOINER)
                for label in _STATEMENT_PERIOD_LABELS
            )
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        for label in _STATEMENT_PERIOD_LABELS:
            period_start, period_end = label_range_period(
                text, label, _STATEMENT_PERIOD_JOINER
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

    def resolve_csv_period_key_with_source(
        self,
        csv_text: str,
        filename: str,
        *,
        account: ResolvedAccount,
    ) -> tuple[str, PeriodSource]:
        from networthcsv.utils.banks.icici.csv import (
            resolve_icici_csv_period_key_with_source,
        )

        return resolve_icici_csv_period_key_with_source(
            csv_text, filename, account=account
        )

    def resolve_csv_period_bounds(
        self,
        csv_text: str,
        *,
        account: ResolvedAccount,
    ) -> tuple[date | None, date | None]:
        from networthcsv.utils.banks.icici.csv import resolve_icici_csv_period_bounds

        return resolve_icici_csv_period_bounds(csv_text, account=account)
