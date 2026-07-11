"""HDFC Regalia Gold credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler


@register("hdfc", "regalia-gold")
class HdfcRegaliaGoldHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your HDFC Bank - HDFC Bank Regalia Gold Credit Card Statement"]
