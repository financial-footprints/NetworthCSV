"""YES statement text cleanup tests."""

from __future__ import annotations

import unittest

from cleanup_support import credit_card_handler


class YesTextCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = credit_card_handler("yes", "ace")

    def test_drops_footer_boilerplate_without_end_marker(self) -> None:
        raw = (
            "Credit Card Statement\n"
            "Statement Date : 16/06/2025\n"
            "Total Amount Due:\n"
            "Rs. 91.68 Cr\n"
            "Statement Details\n"
            "Date  Transaction Details                    Merchant Category Amount (Rs.)\n"
            "Nil Transaction.\n"
            "Making only the minimum payment every month would result\n"
            "from a wide range of options, please visit www.yesrewardz.com\n"
            "YES TOUCH PhoneBanking Number:\n"
            "to +91 95522 20020\n"
            "Page 1 of 4\n"
            "At YES BANK, maintaining confidentiality of your information\n"
            "safety tips continue here\n"
            "Page 2 of 4\n"
            "Important Information:\n"
            "1. Basis RBI circular on Customer Protection\n"
            "YES BANK Credit Cards GSTIN: 27AAACY2068D3ZE\n"
            "Page 3 of 4\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("Statement Date : 16/06/2025", cleaned)
        self.assertIn("Nil Transaction.", cleaned)
        self.assertNotIn("Making only the minimum payment every month", cleaned)
        self.assertNotIn("YES TOUCH PhoneBanking Number", cleaned)
        self.assertNotIn("At YES BANK, maintaining confidentiality", cleaned)
        self.assertNotIn("Important Information:", cleaned)
        self.assertNotIn("Basis RBI circular on Customer Protection", cleaned)
        self.assertNotIn("YES BANK Credit Cards GSTIN", cleaned)

    def test_preserves_transactions_on_later_pages_without_end_marker(self) -> None:
        raw = (
            "Statement Details\n"
            "01/01/2026 SAMPLE MERCHANT ONE 100.00 Dr\n"
            "Page 1 of 3\n"
            "02/01/2026 SAMPLE MERCHANT TWO 200.00 Dr\n"
            "Page 2 of 3\n"
            "At YES BANK, maintaining confidentiality\n"
            "Page 3 of 3\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("SAMPLE MERCHANT ONE", cleaned)
        self.assertIn("SAMPLE MERCHANT TWO", cleaned)
        self.assertNotIn("At YES BANK, maintaining confidentiality", cleaned)

    def test_end_of_statement_marker_trims_trailing_content(self) -> None:
        raw = (
            "Statement Details\n"
            "17/03/2026 PAYMENT RECEIVED BBPS 2,065.08 Cr\n"
            "------------------End of the Statement------------------\n"
            "Page 2 of 4\n"
            "safety text\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("PAYMENT RECEIVED BBPS", cleaned)
        self.assertIn("End of the Statement", cleaned)
        self.assertNotIn("safety text", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
