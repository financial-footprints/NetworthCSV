"""Reusable balance extraction mixins for bank handlers."""

from __future__ import annotations

from networthcsv.utils.banks.helpers.tables import (
    edge_summary_closing,
    edge_summary_opening,
)


class EdgeSummaryBalancesMixin:
    def get_opening_balance(self, text: str) -> str | None:
        return edge_summary_opening(text)

    def get_closing_balance(self, text: str) -> str | None:
        return edge_summary_closing(text)
