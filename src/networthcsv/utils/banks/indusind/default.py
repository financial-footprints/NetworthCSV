"""IndusInd default credit card handler."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks.account_matching import (
    MatchingFields,
    StatementCleanupConfig,
)
from networthcsv.utils.banks import register
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.dates import date_after_label
from networthcsv.utils.banks.helpers.tables import (
    label_next_line_amount,
    total_outstanding_section_amount,
)
from networthcsv.utils.banks.mixins.dates import ContextRangePeriodMixin

_EXCLUDED_STATEMENT_MARKERS = [
    "ANNUAL SPEND SUMMARY",
    "CARD WISE SUMMARY FOR ACCOUNT OF",
    "MONTH WISE SPENDS ON YOUR ACCOUNT",
    "GLIMPSE OF HOW YOU SPENT",
]


@register("indusind", "default")
@register("indusind", "auraedge")
@register("indusind", "amex-epay")
class IndusindDefaultHandler(ContextRangePeriodMixin, CreditCardHandler):
    def period_context(self) -> str:
        return "Statement Period"

    def period_joiner(self) -> str:
        return " To "

    def mail_subjects(self) -> list[str]:
        return ["IndusInd Bank Credit Card"]

    def trim_end(self) -> list[str]:
        return ["Rewards Opening Balance", "Rewards OpeningBalance"]

    def drop_sections(self) -> list[str]:
        return [
            "IMPORTANT MESSAGES:",
            "IMPORTANTMESSAGES:",
            "PROMOTIONAL MESSAGES:",
            "PROMOTIONALMESSAGES:",
            "MARKETING MESSAGE",
            "MARKETINGMESSAGE",
            "NOTE: *Total of points redeemed",
            "With IndusAlerts",
            "Secure your IndusInd Bank Credit Card on-the-go",
            "HOW TO MAKE PAYMENTS",
            "FEES & CHARGES",
            "CREDIT AND CASH WITHDRAWAL LIMITS",
            "Pleasedrawyourcheque",
            "Closest IndusInd Bank ATM Drop Box",
            "Manage your Card with instant Card blocking",
        ]

    def matching_defaults(self) -> MatchingFields:
        defaults = super().matching_defaults()
        return MatchingFields.model_validate(
            {
                **defaults.model_dump(),
                "statement": StatementCleanupConfig.model_validate(
                    {
                        **defaults.statement.model_dump(),
                        "text_not_contains": list(_EXCLUDED_STATEMENT_MARKERS),
                    }
                ).model_dump(),
            }
        )

    def get_statement_date(self, text: str) -> date | None:
        end = super().get_statement_date(text)
        if end is not None:
            return end
        return date_after_label(text, "Statement Date")

    def get_opening_balance(self, text: str) -> str | None:
        return label_next_line_amount(text, "Previous Balance")

    def get_closing_balance(self, text: str) -> str | None:
        return total_outstanding_section_amount(text) or label_next_line_amount(
            text, "Total Amount Due"
        )
