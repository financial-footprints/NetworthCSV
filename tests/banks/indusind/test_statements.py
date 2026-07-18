"""IndusInd statement balance extraction tests."""

from __future__ import annotations

import unittest

from cleanup_support import FIXTURES_ROOT, account as make_account
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.text import text_not_contains_violated

_ANNUAL_SUMMARY_MARKERS = [
    "ANNUAL SPEND SUMMARY",
    "CARD WISE SUMMARY FOR ACCOUNT OF",
    "MONTH WISE SPENDS ON YOUR ACCOUNT",
]


class IndusindStatementBalanceTests(unittest.TestCase):
    def test_previous_balance_next_line(self) -> None:
        text = (
            "Previous Balance\n"
            "0.00 DR\n"
            "Total Amount Due\n"
            "990.00 CR\n"
            "Total Outstanding\n"
            "(Including Loans)\n"
            "990.00 CR\n"
        )
        account = make_account(
            bank="indusind",
            variant="default",
            account_number="1234",
            passwords=["x"],
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-990.00")

    def test_total_outstanding_scrambled_layout(self) -> None:
        text = (
            "Previous Balance\n"
            "1200.00 CR\n"
            "Total Amount Due\n"
            "550.00 CR\n"
            "22/07/2025 GST @ 18%                       0          .50 DR  Total Outstanding\n"
            "                                                                   (includingLoans)\n"
            "   Total                                      0         3.50\n"
            "                                                                    549.50 CR\n"
            "   Rewards OpeningBalance(Points) PointsEarned PointsRedeemed* ClosingBalance(Points)\n"
        )
        handler = get_handler("indusind", "auraedge")
        closing = handler.get_closing_balance(text)
        self.assertEqual(closing, "-549.50")

    def test_total_outstanding_on_total_row(self) -> None:
        text = (
            "Previous Balance\n"
            "400.00 DR\n"
            "Total Amount Due\n"
            "125.00 DR\n"
            "25/04/2025 SAMPLE MERCHANT 356  DEPARTMENTAL 0       500.00 DR Total Outstanding\n"
            "                                   STORES                          (includingLoans)\n"
            "   Total                                      0        500.00       125.00 DR\n"
            "   Rewards OpeningBalance(Points) PointsEarned PointsRedeemed* ClosingBalance(Points)\n"
        )
        handler = get_handler("indusind", "amex-epay")
        closing = handler.get_closing_balance(text)
        self.assertEqual(closing, "125.00")

    def test_total_outstanding_stops_before_invoice(self) -> None:
        text = (
            "Previous Balance\n"
            "0.00 DR\n"
            "Total Amount Due\n"
            "950.00 DR\n"
            "Total Outstanding\n"
            "(includingLoans)\n"
            "950.00 DR\n"
            "MS NEHA GUPTA\n"
            "Invoice and Credit note No : 8123456789012345678\n"
            "PaymentDueDate Min.AmountDue\n"
            "07/03/2022 80.00\n"
        )
        handler = get_handler("indusind", "amex-epay")
        closing = handler.get_closing_balance(text)
        self.assertEqual(closing, "950.00")


class IndusindMatchingDefaultsTests(unittest.TestCase):
    def test_matching_defaults_reject_annual_spend_summary(self) -> None:
        handler = get_handler("indusind", "auraedge")
        defaults = handler.matching_defaults()
        self.assertEqual(
            defaults.statement.text_not_contains,
            _ANNUAL_SUMMARY_MARKERS,
        )
        summary_text = (FIXTURES_ROOT / "indusind/annual-spend-summary.txt").read_text(
            encoding="utf-8"
        )
        sanitized = handler.clean_text(summary_text)
        self.assertTrue(
            text_not_contains_violated(
                sanitized,
                defaults.statement.text_not_contains,
            )
        )

    def test_matching_defaults_allow_real_statement(self) -> None:
        handler = get_handler("indusind", "auraedge")
        defaults = handler.matching_defaults()
        statement_text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        sanitized = handler.clean_text(statement_text)
        self.assertFalse(
            text_not_contains_violated(
                sanitized,
                defaults.statement.text_not_contains,
            )
        )


if __name__ == "__main__":
    _ = unittest.main()
