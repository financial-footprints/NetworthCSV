"""Federal Edge credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.federal.default import FederalDefaultHandler
from networthcsv.utils.banks.helpers.jupiter import inject_edge_summary_labels
from networthcsv.utils.banks.helpers.text import END_OF_TRANSACTIONS_TRIM_MARKER


@register("federal", "edge")
class FederalEdgeHandler(FederalDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Edge Federal Bank Credit Card Statement"]

    def trim_end(self) -> list[str]:
        return [END_OF_TRANSACTIONS_TRIM_MARKER]

    def drop_sections(self) -> list[str]:
        return ["IMPORTANT INFORMATION", "Issued by"]

    def clean_text(self, raw: str) -> str:
        return inject_edge_summary_labels(super().clean_text(raw))
