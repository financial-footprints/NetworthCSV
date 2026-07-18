"""Tests for ICICI Amazon Pay credit card statement trimming."""

from __future__ import annotations

import unittest

from cleanup_support import FIXTURES_ROOT
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.helpers.text import text_contains_present

_FIXTURES = FIXTURES_ROOT / "icici" / "amazon"


class IciciAmazonTrimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = get_handler("icici", "amazon")
        assert isinstance(cls.handler, CreditCardHandler)
        cls.sample = (_FIXTURES / "sample.txt").read_text(encoding="utf-8")
        cls.with_earnings = (_FIXTURES / "with_earnings.txt").read_text(
            encoding="utf-8"
        )
        cls.multicolumn = (_FIXTURES / "multicolumn_earnings_first.txt").read_text(
            encoding="utf-8"
        )

    def test_trim_ends_at_amazon_pay_balance(self) -> None:
        cleaned = self.handler.clean_text(self.with_earnings)
        self.assertIn("Amazon Pay balance*", cleaned)
        self.assertIn("Earnings transfered to", cleaned)
        self.assertIn("15/04/2024 1000000002 UPI Payment Received", cleaned)
        self.assertNotIn("Safe Banking Tips", cleaned)
        self.assertNotIn("MOST IMPORTANT TERMS AND CONDITIONS (MITC)", cleaned)
        self.assertNotIn("Page 1 of 6", cleaned)

    def test_trim_falls_back_to_mitc_without_earnings(self) -> None:
        raw = (
            "txn line\n"
            "footer junk\n"
            "MOST IMPORTANT TERMS AND CONDITIONS (MITC)\n"
            "legal text"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("MOST IMPORTANT TERMS AND CONDITIONS (MITC)", cleaned)
        self.assertNotIn("legal text", cleaned)

    def test_legacy_sample_without_earnings_or_mitc(self) -> None:
        cleaned = self.handler.clean_text(self.sample)
        self.assertIn("15/09/2021 88472910561 COOPERATIVE STORE MEMBERSHIP IN", cleaned)
        self.assertIn("Page 1 of 7", cleaned)

    def test_multicolumn_earnings_before_spends_uses_mitc_trim(self) -> None:
        cleaned = self.handler.clean_text(self.multicolumn)
        self.assertIn("123454XXXXXX7890", cleaned)
        self.assertIn("13/08/2022 6477712643 SAMPLE MERCHANT PURCHASE IN", cleaned)
        self.assertIn("Invoice No: 2099120900019246", cleaned)
        self.assertIn("MOST IMPORTANT TERMS AND CONDITIONS (MITC)", cleaned)
        self.assertNotIn("SPENDS OVERVIEW", cleaned)
        self.assertNotIn("# International Spends", cleaned)
        self.assertNotIn("legal footer text", cleaned)

    def test_multicolumn_fixture_matches_text_contains(self) -> None:
        cleaned = self.handler.clean_text(self.multicolumn)
        self.assertTrue(text_contains_present(cleaned, ["7148"]))


class IciciAmazonInvoiceReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = get_handler("icici", "amazon")

    def test_multicolumn_fixture_invoice_reference(self) -> None:
        text = (_FIXTURES / "multicolumn_earnings_first.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(self.handler.get_statement_reference(text), "2099120900019246")

    def test_sample_fixture_invoice_reference(self) -> None:
        text = (_FIXTURES / "sample.txt").read_text(encoding="utf-8")
        self.assertEqual(self.handler.get_statement_reference(text), "2091101200013852")
