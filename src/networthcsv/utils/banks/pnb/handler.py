"""PNB credit card handler facade (auto-detects PDF layout v1 vs v2)."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.pnb.common import DROP_SECTIONS, MAIL_SUBJECTS, TRIM_END
from networthcsv.utils.banks.pnb.default import get_layout


@register("pnb", "default")
@register("pnb", "platinum")
class PnbHandler(CreditCardHandler):
    def mail_subjects(self) -> list[str]:
        return list(MAIL_SUBJECTS)

    def trim_end(self) -> list[str]:
        return list(TRIM_END)

    def drop_sections(self) -> list[str]:
        return list(DROP_SECTIONS)

    def clean_text(self, raw: str) -> str:
        return get_layout(raw).clean_text(raw)

    def get_statement_date(self, text: str) -> date | None:
        return get_layout(text).get_statement_date(text)

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        return get_layout(text).get_statement_period(text)

    def get_opening_balance(self, text: str) -> str | None:
        return get_layout(text).get_opening_balance(text)

    def get_closing_balance(self, text: str) -> str | None:
        return get_layout(text).get_closing_balance(text)

    def get_statement_reference(self, text: str) -> str | None:
        return get_layout(text).get_invoice_number(text)
