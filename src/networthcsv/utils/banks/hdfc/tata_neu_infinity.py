"""HDFC Tata Neu Infinity credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler, _HDFC_DROP_SECTIONS
from networthcsv.utils.banks.helpers.tables import (
    equation_first_after,
    single_amount_after,
)

_TATA_NEU_EXTRA_DROP_SECTIONS = [
    "NeuCoins with Bank Opening NeuCoins",
    "Eligible for EMI",
    "CONVERT TO EMI",
]


@register("hdfc", "tata-neu-infinity")
class HdfcTataNeuInfinityHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your HDFC Bank - Tata Neu Infinity HDFC Bank Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return ["Bonus NeuCoins Summary"]

    def drop_sections(self) -> list[str]:
        return [*_HDFC_DROP_SECTIONS, *_TATA_NEU_EXTRA_DROP_SECTIONS]

    def get_opening_balance(self, text: str) -> str | None:
        return equation_first_after(text, "PREVIOUS STATEMENT DUES")

    def get_closing_balance(self, text: str) -> str | None:
        return single_amount_after(text, "TOTAL AMOUNT DUE")
