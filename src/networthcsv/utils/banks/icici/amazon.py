"""ICICI Amazon credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.icici.default import (
    IciciDefaultHandler,
    _ICICI_DROP_SECTIONS,
)


@register("icici", "amazon")
class IciciAmazonHandler(IciciDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Amazon Pay ICICI Bank Credit Card Statement for the period"]

    def drop_sections(self) -> list[str]:
        return [*_ICICI_DROP_SECTIONS, "EARNINGS"]
