"""ICICI Amazon credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.helpers.text import (
    purge_drop_sections,
    sanitize_statement_text,
    trim_by_markers,
)
from networthcsv.utils.banks.icici.default import (
    IciciDefaultHandler,
    _ICICI_DROP_SECTIONS,
)


@register("icici", "amazon")
class IciciAmazonHandler(IciciDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return [
            "Amazon Pay ICICI Bank Credit Card Statement for the period",
            "ICICI Bank Credit Card Statement for the period",
        ]

    def trim_end(self) -> list[str]:
        return ["Earnings transfered to", "Amazon Pay balance*"]

    def drop_sections(self) -> list[str]:
        return [*_ICICI_DROP_SECTIONS, "EARNINGS"]

    def clean_text(self, raw: str) -> str:
        trimmed = trim_by_markers(raw, trim_end=self.trim_end())
        if not any(marker in raw for marker in self.trim_end()):
            trimmed = trim_by_markers(raw, trim_end=super().trim_end())
        sanitized = sanitize_statement_text(trimmed)
        return purge_drop_sections(sanitized, drop_sections=self.drop_sections())
