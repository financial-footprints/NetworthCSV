"""Tests for IDFC WOW credit card statement handler."""

from __future__ import annotations

import unittest
from datetime import date

from cleanup_support import FIXTURES_ROOT, account as make_account
from networthcsv.utils.banks.period import (
    extract_statement_date,
    extract_statement_period,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.banks.idfc.summary import (
    join_orphan_cr_dr,
    normalize_cr_dr_layout,
)

_FIXTURES = FIXTURES_ROOT / "idfc" / "wow"


class IdfcWowStatementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = get_handler("idfc", "wow")
        assert isinstance(cls.handler, CreditCardHandler)
        cls.classic = (_FIXTURES / "classic-2023-08.txt").read_text(encoding="utf-8")
        cls.modern_2025 = (_FIXTURES / "modern-2025-11.txt").read_text(encoding="utf-8")
        cls.modern_2026 = (_FIXTURES / "modern-2026-04.txt").read_text(encoding="utf-8")
        cls.scrambled_2023 = (_FIXTURES / "scrambled-2023-10.txt").read_text(
            encoding="utf-8"
        )
        cls.classic_detached_cr_2023 = (
            _FIXTURES / "classic-detached-cr-2023-10.txt"
        ).read_text(encoding="utf-8")
        cls.account = make_account(
            bank="idfc",
            variant="wow",
            account_number="1234",
            passwords=["x"],
        )

    def test_classic_statement_date_and_period(self) -> None:
        parsed = extract_statement_date(self.classic, account=self.account)
        self.assertEqual(parsed, date(2021, 6, 17))
        period_start, period_end = extract_statement_period(
            self.classic, account=self.account
        )
        self.assertEqual(period_start, date(2021, 5, 18))
        self.assertEqual(period_end, date(2021, 6, 17))

    def test_modern_2025_statement_date_and_period(self) -> None:
        parsed = extract_statement_date(self.modern_2025, account=self.account)
        self.assertEqual(parsed, date(2021, 11, 17))
        period_start, period_end = extract_statement_period(
            self.modern_2025, account=self.account
        )
        self.assertEqual(period_start, date(2021, 10, 18))
        self.assertEqual(period_end, date(2021, 11, 17))

    def test_modern_2026_statement_date_and_period(self) -> None:
        parsed = extract_statement_date(self.modern_2026, account=self.account)
        self.assertEqual(parsed, date(2021, 6, 17))
        period_start, period_end = extract_statement_period(
            self.modern_2026, account=self.account
        )
        self.assertEqual(period_start, date(2021, 5, 18))
        self.assertEqual(period_end, date(2021, 6, 17))

    def test_classic_balances(self) -> None:
        opening = self.handler.get_opening_balance(self.classic)
        closing = self.handler.get_closing_balance(self.classic)
        self.assertEqual(opening, "-500.00")
        self.assertEqual(closing, "-350.00")

    def test_modern_2025_balances(self) -> None:
        opening = self.handler.get_opening_balance(self.modern_2025)
        closing = self.handler.get_closing_balance(self.modern_2025)
        self.assertEqual(opening, "-500.00")
        self.assertEqual(closing, "-350.00")

    def test_modern_2026_balances(self) -> None:
        opening = self.handler.get_opening_balance(self.modern_2026)
        closing = self.handler.get_closing_balance(self.modern_2026)
        self.assertEqual(opening, "-500.00")
        self.assertEqual(closing, "-350.00")

    def test_scrambled_2023_10_balances(self) -> None:
        opening = self.handler.get_opening_balance(self.scrambled_2023)
        closing = self.handler.get_closing_balance(self.scrambled_2023)
        self.assertEqual(opening, "-12345.67")
        self.assertEqual(closing, "-10000.00")

    def test_classic_detached_cr_2023_10_balances(self) -> None:
        opening = self.handler.get_opening_balance(self.classic_detached_cr_2023)
        closing = self.handler.get_closing_balance(self.classic_detached_cr_2023)
        self.assertEqual(opening, "-12345.67")
        self.assertEqual(closing, "-10000.00")

    def test_join_orphan_cr_dr(self) -> None:
        raw = "r12,345.67\nCR\nr10,000.00 CR"
        self.assertEqual(join_orphan_cr_dr(raw), "r12,345.67 CR\nr10,000.00 CR")

    def test_normalize_cr_dr_layout_detached_suffix(self) -> None:
        raw = (
            "r0.00              r12,345.67 r100.00  r0.00    r0.00   r0.00  r10,000.00\n"
            "Payment Due Date   CR                                            CR"
        )
        normalized = normalize_cr_dr_layout(raw)
        self.assertIn("r12,345.67 CR", normalized)
        self.assertIn("r10,000.00 CR", normalized)

    def test_cleanup_retains_transactions(self) -> None:
        raw = (
            "Credit Card Statement\n"
            "YOUR TRANSACTIONS\n"
            "16/05/2021 Sample Merchant 100.00\n"
            "SPECIAL BENEFITS ON YOUR CARD\n"
            "marketing\n"
            "IMPORTANT INFORMATION\n"
            "legal text\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("16/05/2021 Sample Merchant 100.00", cleaned)
        self.assertNotIn("marketing", cleaned)
        self.assertIn("IMPORTANT INFORMATION", cleaned)
        self.assertNotIn("legal text", cleaned)

    def test_drops_payment_modes_and_comparison_tables(self) -> None:
        raw = (
            "Credit Card Statement\n"
            "Statement Date:   17/02/2025\n"
            "PAYMENT MODES\n"
            "Pay via our new Mobile App\n"
            "YOUR TRANSACTIONS\n"
            "15 Feb 25       SAMPLE MERCHANT               512.78 DR\n"
            "Refer this Credit Card to your friends\n"
            "CHECK OUT WHY.\n"
            "comparison table text\n"
            "IMPORTANT INFORMATION\n"
            "legal text\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("Statement Date:", cleaned)
        self.assertIn("SAMPLE MERCHANT", cleaned)
        self.assertNotIn("PAYMENT MODES", cleaned)
        self.assertNotIn("Pay via our new Mobile App", cleaned)
        self.assertNotIn("Refer this Credit Card", cleaned)
        self.assertNotIn("CHECK OUT WHY", cleaned)
        self.assertNotIn("comparison table text", cleaned)
        self.assertIn("IMPORTANT INFORMATION", cleaned)
        self.assertNotIn("legal text", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
