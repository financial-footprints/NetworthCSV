"""Federal default credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.mixins.balances import EdgeSummaryBalancesMixin
from networthcsv.utils.banks.mixins.dates import TopRangeDateMixin


@register("federal", "default")
class FederalDefaultHandler(
    EdgeSummaryBalancesMixin, TopRangeDateMixin, CreditCardHandler
):
    def mail_subjects(self) -> list[str]:
        return ["Federal Bank Credit Card Statement"]
