"""ICICI Amazon credit card handler."""

from __future__ import annotations

import re

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

_SPENDS_OVERVIEW_MARKER = "SPENDS OVERVIEW"
_SPENDS_OVERVIEW_PHRASE = re.compile(r"SPENDS\s+OVERVIEW", re.IGNORECASE)
_AMAZON_DROP_SECTIONS = [
    section for section in _ICICI_DROP_SECTIONS if section != _SPENDS_OVERVIEW_MARKER
]


def _earnings_markers_before_spends(raw: str, earnings_markers: list[str]) -> bool:
    spends_idx = raw.find(_SPENDS_OVERVIEW_MARKER)
    if spends_idx == -1:
        return False
    return any(
        raw.find(marker) != -1 and raw.find(marker) < spends_idx
        for marker in earnings_markers
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
        return [*_AMAZON_DROP_SECTIONS, "EARNINGS"]

    def clean_text(self, raw: str) -> str:
        earnings_markers = self.trim_end()
        if not any(marker in raw for marker in earnings_markers):
            trim_end = super().trim_end()
        elif _earnings_markers_before_spends(raw, earnings_markers):
            trim_end = super().trim_end()
        else:
            trim_end = earnings_markers
        trimmed = trim_by_markers(raw, trim_end=trim_end)
        sanitized = sanitize_statement_text(trimmed)
        purged = purge_drop_sections(sanitized, drop_sections=self.drop_sections())
        return _SPENDS_OVERVIEW_PHRASE.sub("", purged)
