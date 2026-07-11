"""HDFC Diners credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler


@register("hdfc", "diners-privilege")
class HdfcDinersHandler(HdfcDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your HDFC Bank - Diners Club International Credit Card Statement"]
