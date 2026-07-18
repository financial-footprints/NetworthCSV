"""PNB statement PDF layout v2 (marketing pages before statement block)."""

from __future__ import annotations

import re
from datetime import date

from networthcsv.utils.banks.helpers.amounts import first_not_none
from networthcsv.utils.banks.helpers.dates import (
    context_range_period,
    date_after_label,
    first_not_none_date,
    label_single_date_end,
    parse_date_string,
)
from networthcsv.utils.banks.helpers.tables import (
    label_single_amount,
    summary_table_column,
)
from networthcsv.utils.banks.pnb.common import INVOICE_NO_LABEL
from networthcsv.utils.banks.pnb.default._text import (
    prepare_statement_text,
    trim_statement_body,
)
from networthcsv.utils.banks.pnb.invoice import extract_invoice_number
from networthcsv.utils.banks.pnb.stacked import stacked_label_amount

_STANDALONE_PERIOD_LINE = re.compile(
    r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(\d{1,2}-[A-Za-z]{3}-\d{4})",
    re.IGNORECASE,
)


class LayoutV2:
    def trim_start(self) -> list[str]:
        return [INVOICE_NO_LABEL]

    def clean_text(self, raw: str) -> str:
        return prepare_statement_text(raw, trim_start=self.trim_start())

    def _body(self, text: str) -> str:
        return trim_statement_body(text, trim_start=self.trim_start())

    def get_statement_date(self, text: str) -> date | None:
        body = self._body(text)
        return first_not_none_date(
            label_single_date_end(body, "Invoice Date :"),
            date_after_label(body, "Invoice Date :"),
        )

    def _period_from_standalone_line(
        self, text: str
    ) -> tuple[date | None, date | None]:
        body = self._body(text)
        for line in body.split("\n"):
            match = _STANDALONE_PERIOD_LINE.search(line)
            if match is None:
                continue
            period_start = parse_date_string(match.group(1))
            period_end = parse_date_string(match.group(2))
            if period_start is not None and period_end is not None:
                return period_start, period_end
        return None, None

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        body = self._body(text)
        period_start, period_end = context_range_period(body, "From", " to ")
        if period_start is not None and period_end is not None:
            return period_start, period_end
        standalone = self._period_from_standalone_line(text)
        if standalone != (None, None):
            return standalone
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None

    def get_opening_balance(self, text: str) -> str | None:
        body = self._body(text)
        return summary_table_column(
            body,
            context="Account Summary",
            column="Previous Balance",
        )

    def get_closing_balance(self, text: str) -> str | None:
        body = self._body(text)
        return first_not_none(
            summary_table_column(
                body,
                context="Account Summary",
                column="Total Amount Due for Month",
            ),
            stacked_label_amount(body, "Total Amount Due for Month"),
            stacked_label_amount(body, "Total Amount Due"),
            label_single_amount(body, "Total Amount Due for Month"),
            label_single_amount(body, "Total Amount Due :"),
        )

    def get_invoice_number(self, text: str) -> str | None:
        return extract_invoice_number(self._body(text))
