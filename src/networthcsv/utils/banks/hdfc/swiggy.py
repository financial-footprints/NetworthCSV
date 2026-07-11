"""HDFC Swiggy credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler


@register("hdfc", "swiggy")
class HdfcSwiggyHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["HDFC Bank - Swiggy HDFC Bank Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return ["Cashback Summary"]
