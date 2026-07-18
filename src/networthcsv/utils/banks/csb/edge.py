"""CSB Edge credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.csb.default import CsbDefaultHandler
from networthcsv.utils.banks.helpers.jupiter import inject_edge_summary_labels
from networthcsv.utils.banks.helpers.text import END_OF_TRANSACTIONS_TRIM_MARKER


@register("csb", "edge")
class CsbEdgeHandler(CsbDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Edge CSB Bank RuPay Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return [END_OF_TRANSACTIONS_TRIM_MARKER]

    def clean_text(self, raw: str) -> str:
        return inject_edge_summary_labels(super().clean_text(raw))
