"""HDFC Regalia credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler


@register("hdfc", "regalia")
class HdfcRegaliaHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your HDFC Bank - Regalia MasterCard Credit Card Statement"]
