"""ICICI statement text cleanup tests."""

from __future__ import annotations

import unittest

from helpers import credit_card_handler


class IciciTextCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = credit_card_handler("icici", "platinum")

    def test_drops_spends_overview_and_offers(self) -> None:
        raw = (
            "STATEMENT DATE\n"
            "January 13, 2023\n"
            "STATEMENT SUMMARY\n"
            "Total Amount due\n"
            "953.00 CR\n"
            "SPENDS OVERVIEW  Date   SerNo. Transaction Details Reward Intl.# Amount (in )\n"
            "4035XXXXXXXX1005\n"
            "03/01/2023 7025882248 SAMPLE MERCHANT MUMBAI IN 0      5.00\n"
            "# International Spends\n"
            "100%\n"
            "Others-100%\n"
            "www.icicibank.com/offers\n"
            "T&C apply\n"
            "For any query, you may write to us on customer.care@icicibank.com\n"
            "MOST IMPORTANT TERMS AND CONDITIONS (MITC)\n"
            "legal text\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("STATEMENT SUMMARY", cleaned)
        self.assertIn("SAMPLE MERCHANT MUMBAI IN", cleaned)
        self.assertNotIn("SPENDS OVERVIEW", cleaned)
        self.assertNotIn("# International Spends", cleaned)
        self.assertNotIn("Others-100%", cleaned)
        self.assertNotIn("www.icicibank.com/offers", cleaned)
        self.assertNotIn("For any query, you may write to us on customer.care", cleaned)
        self.assertIn("MOST IMPORTANT TERMS AND CONDITIONS (MITC)", cleaned)
        self.assertNotIn("legal text", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
