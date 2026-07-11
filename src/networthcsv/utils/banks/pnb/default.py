"""PNB credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
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

_PNB_DROP_SECTIONS = [
    "*TAD for the month consists of current month purchases, charges, cash advances and amount of BT/EMI due for the month if any. Making only the minimum payment if any month would result in the repayment stretching over subsequent Always get MORE with months with consequent interest payment on your outstanding balance. Please examine your statement immediately upon receipt. If no error is reported within 60 days from the date PNB Credit Cards of statement, the account will be considered correct. Place of supply : PNB, Credit Card Processing Center, Ground Floor, C-24, Sec-58, Noida, Uttar Pradesh 201301, State Code : 09 GSTIN No.: 07AAACP0165G3ZP Registered Address : Punjab National Bank, Plot No. 7, East Block Road, Bhikaji Cama Place, New Delhi, New Delhi, Delhi, 110066 State Code : 07",
    "Presenting Rupay Platinum",
    "PNB GENIE",
    "Scan and download",
    "Always get MORE",
    "Reward points details",
    "Why pay in Rupees",
    "CAUTION :",
    "Please make all Cheque",
]


@register("pnb", "default")
@register("pnb", "platinum")
class PnbHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your PNB Credit Card Statement for the month"]

    def trim_end(self) -> list[str]:
        return ["********** End of Statement **********"]

    def drop_sections(self) -> list[str]:
        return list(_PNB_DROP_SECTIONS)

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
