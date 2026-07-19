"""HDFC statement text cleanup tests."""

from __future__ import annotations

import unittest

from helpers import credit_card_handler


class HdfcTextCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = credit_card_handler("hdfc", "default")

    def test_drops_header_boilerplate_and_keeps_summary(self) -> None:
        raw = (
            "Regalia Mastercard Credit Card Statement\n"
            "Statement Date:20/01/2023\n"
            "In case you wish to update the personal details,please write a letter\n"
            "to The Manager, HDFC Bank Card Division\n"
            "Note : The  Available Credit Limit  shown in this\n"
            "statement takes into account charges incurred but\n"
            "If the  Minimum Amount Due  or  Part Amount  less\n"
            "than the  Total Amount Due  is paid, Interest\n"
            "To Hotlist your Credit Card, login into Netbanking\n"
            "with Credit Information Companies (CICs) are approved\n"
            "Account Summary\n"
            "Opening Balance   Credits   Debits   Total Dues\n"
            "79,187.82 84,275.00 199.00   -4,888.18\n"
            "16-Jan-2023 SAMPLE MERCHANT ONE 199.00 DR\n"
            "Making only the minimum payment every month would result\n"
            "Statement and Payment MITC (Most Impt Terms &\n"
            "legal footer text\n"
            "Reward Points Summary\n"
            "points table\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("Account Summary", cleaned)
        self.assertIn("SAMPLE MERCHANT ONE", cleaned)
        self.assertNotIn("In case you wish to update the personal details", cleaned)
        self.assertNotIn("To Hotlist your Credit Card", cleaned)
        self.assertNotIn("Credit Information Companies", cleaned)
        self.assertNotIn("Making only the minimum payment every month", cleaned)
        self.assertNotIn("Statement and Payment MITC", cleaned)
        self.assertIn("Reward Points Summary", cleaned)
        self.assertNotIn("points table", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
