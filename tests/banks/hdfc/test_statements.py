"""HDFC statement balance extraction tests."""

from __future__ import annotations

import unittest
from datetime import date

from helpers import FIXTURES_ROOT, account as make_account
from networthcsv.pipeline.cleanup.keeper import statement_collapse_key
from networthcsv.utils.banks.period import (
    extract_statement_date,
    extract_statement_period,
    resolve_period_bounds,
    resolve_period_key,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.hdfc.default import HdfcDefaultHandler
from networthcsv.utils.banks.hdfc.swiggy import HdfcSwiggyHandler


class HdfcStatementBalanceTests(unittest.TestCase):
    def test_regalia_split_account_summary_headers(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                      0.00     5.00    12,350.67  0.00    12,345.67\n"
        )
        account = make_account(
            bank="hdfc", account_number="1234", passwords=["x"], variant="regalia"
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "12345.67")

    def test_diners_account_summary_with_credit_closing(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     11,111.11 11,211.11 0.00     0.00     -555.55\n"
        )
        account = make_account(
            bank="hdfc",
            account_number="1234",
            passwords=["x"],
            variant="diners-privilege",
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "11111.11")
        self.assertEqual(closing, "-555.55")

    def test_diners_account_summary_mixed_signs(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     -2,222.22 0.00    13,333.33  0.00    11,111.11\n"
        )
        account = make_account(
            bank="hdfc",
            account_number="1234",
            passwords=["x"],
            variant="diners-privilege",
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "-2222.22")
        self.assertEqual(closing, "11111.11")

    def test_diners_negative_opening_and_closing(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     -4,444.44 0.00     2,222.22  0.00    -2,222.22\n"
        )
        account = make_account(
            bank="hdfc",
            account_number="1234",
            passwords=["x"],
            variant="diners-privilege",
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "-4444.44")
        self.assertEqual(closing, "-2222.22")


class HdfcSwiggyCollapsedHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="hdfc", account_number="1234", passwords=["x"], variant="swiggy"
        )
        cls.text = (
            FIXTURES_ROOT / "hdfc/swiggy/sample-collapsed-header.txt"
        ).read_text(encoding="utf-8")

    def test_collapsed_header_statement_date(self) -> None:
        parsed = extract_statement_date(self.text, account=self.account)
        self.assertEqual(parsed, date(2024, 6, 20))

    def test_collapsed_header_statement_period_end(self) -> None:
        period_start, period_end = extract_statement_period(
            self.text,
            account=self.account,
        )
        self.assertEqual(period_start, date(2024, 5, 21))
        self.assertEqual(period_end, date(2024, 6, 20))

    def test_collapsed_header_resolved_period_bounds(self) -> None:
        period_start, period_end, approximate = resolve_period_bounds(
            self.text,
            account=self.account,
        )
        self.assertEqual(period_start, "21-05-2024")
        self.assertEqual(period_end, "20-06-2024")
        self.assertTrue(approximate)


class HdfcSwiggyIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="hdfc", account_number="1234", passwords=["x"], variant="swiggy"
        )
        handler = get_handler(cls.account.bank, cls.account.variant)
        assert isinstance(handler, HdfcSwiggyHandler)
        cls.handler = handler
        cls.modern = cls.handler.clean_text(
            (FIXTURES_ROOT / "hdfc/swiggy/modern-may-2026.txt").read_text(
                encoding="utf-8"
            )
        )
        cls.duplicate = cls.handler.clean_text(
            (FIXTURES_ROOT / "hdfc/swiggy/duplicate-may-2026.txt").read_text(
                encoding="utf-8"
            )
        )

    def test_layout_detection(self) -> None:
        self.assertEqual(self.handler.swiggy_layout_id(self.modern), "v1")
        self.assertEqual(self.handler.swiggy_layout_id(self.duplicate), "v2")
        self.assertEqual(self.handler.hdfc_layout_id(self.modern), "v1")
        self.assertEqual(self.handler.hdfc_layout_id(self.duplicate), "v2")

    def test_v2_and_v1_balances_after_clean_text(self) -> None:
        self.assertEqual(self.handler.get_opening_balance(self.modern), "-137.30")
        self.assertEqual(self.handler.get_closing_balance(self.modern), "277.00")
        self.assertEqual(self.handler.get_opening_balance(self.duplicate), "-137.30")
        self.assertEqual(self.handler.get_closing_balance(self.duplicate), "277.00")

    def test_modern_and_duplicate_share_aan_invoice_collapse_key(self) -> None:
        modern_ref = self.handler.get_statement_reference(self.modern)
        duplicate_ref = self.handler.get_statement_reference(self.duplicate)
        self.assertEqual(modern_ref, "0001010610002115678")
        self.assertEqual(duplicate_ref, modern_ref)
        modern_key = statement_collapse_key(self.modern, self.account)
        duplicate_key = statement_collapse_key(self.duplicate, self.account)
        self.assertEqual(modern_key[0], "invoice")
        self.assertEqual(modern_key, duplicate_key)

    def test_same_line_total_amount_due_header(self) -> None:
        text = (
            "Billing Period\n"
            "TOTAL AMOUNT DUE C277.00\n"
            "MINIMUM DUE\n"
            "C200.00\n"
            "PREVIOUS STATEMENT DUES\n"
            "C-,137.30 C45.80 C460.00 C0.00\n"
        )
        self.assertEqual(self.handler.swiggy_layout_id(text), "v1")
        self.assertEqual(self.handler.get_closing_balance(text), "277.00")

    def test_merged_same_line_total_amount_due_takes_first_amount(self) -> None:
        text = (
            "Billing Period\n"
            "TOTAL AMOUNT DUE C277.00 MINIMUM DUE C200.00\n"
            "PREVIOUS STATEMENT DUES\n"
            "C-,137.30 C45.80 C460.00 C0.00\n"
        )
        self.assertEqual(self.handler.get_closing_balance(text), "277.00")

    def test_merged_next_line_total_amount_due_takes_first_amount(self) -> None:
        text = (
            "Billing Period\n"
            "TOTAL AMOUNT DUE\n"
            "C277.00 MINIMUM DUE C200.00\n"
            "PREVIOUS STATEMENT DUES\n"
            "C-,137.30 C45.80 C460.00 C0.00\n"
        )
        self.assertEqual(self.handler.get_closing_balance(text), "277.00")

    def test_split_label_total_amount_due_across_lines(self) -> None:
        text = (
            "Billing Period\n"
            "TOTAL\n"
            "AMOUNT\n"
            "DUE\n"
            "C277.00\n"
            "MINIMUM DUE\n"
            "C200.00\n"
            "PREVIOUS STATEMENT DUES\n"
            "C-,137.30 C45.80 C460.00 C0.00\n"
        )
        self.assertEqual(self.handler.swiggy_layout_id(text), "v1")
        self.assertEqual(self.handler.get_closing_balance(text), "277.00")


class HdfcV2GuidelineLayoutTests(unittest.TestCase):
    """Bank-wide HDFC v2 styling applies to every variant handler."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = (FIXTURES_ROOT / "hdfc/default/v2-guideline-may-2026.txt").read_text(
            encoding="utf-8"
        )
        cls.variants = (
            "default",
            "regalia",
            "regalia-gold",
            "diners-privilege",
            "tata-neu-infinity",
            "swiggy",
        )

    def test_all_variants_detect_v2_and_parse_balances(self) -> None:
        for variant in self.variants:
            with self.subTest(variant=variant):
                account = make_account(
                    bank="hdfc", account_number="1234", passwords=["x"], variant=variant
                )
                handler = get_handler(account.bank, account.variant)
                assert isinstance(handler, HdfcDefaultHandler)
                text = handler.clean_text(self.raw)
                self.assertEqual(handler.hdfc_layout_id(text), "v2")
                self.assertEqual(handler.get_opening_balance(text), "-137.30")
                self.assertEqual(handler.get_closing_balance(text), "277.00")
                self.assertEqual(
                    handler.get_statement_reference(text), "0001017100000593848"
                )
                self.assertEqual(handler.get_statement_date(text), date(2026, 5, 20))


class HdfcAnnualStatementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="hdfc", account_number="1234", passwords=["x"], variant="default"
        )
        cls.text = (FIXTURES_ROOT / "hdfc/default/yearly-sample.txt").read_text(
            encoding="utf-8"
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)

    def test_year_display_is_fiscal(self) -> None:
        self.assertEqual(self.handler.year_display(), "fiscal_year")

    def test_annual_mail_subjects_merged_in_defaults(self) -> None:
        defaults = self.handler.matching_defaults()
        self.assertIn("Year End Statement Summary", defaults.mail.subjects)

    def test_is_annual_statement(self) -> None:
        self.assertTrue(self.handler.is_annual_statement(self.text))

    def test_is_annual_statement_from_period_pattern_only(self) -> None:
        text = (
            "Account Summary for the period from APRIL-24 to MARCH-25\n"
            "000123456XXXXXX7890"
        )
        self.assertTrue(self.handler.is_annual_statement(text))

    def test_annual_period(self) -> None:
        period = self.handler.get_annual_period(self.text)
        self.assertIsNotNone(period)
        assert period is not None
        self.assertEqual(period[0], date(2024, 4, 1))
        self.assertEqual(period[1], date(2025, 3, 31))

    def test_resolve_annual_period(self) -> None:
        period = resolve_period_key(self.text, "sample.pdf", account=self.account)
        self.assertEqual(period, "FY24-2025")

    def test_annual_statement_date_is_period_end(self) -> None:
        parsed = extract_statement_date(self.text, account=self.account)
        self.assertEqual(parsed, date(2025, 3, 31))

    def test_annual_statement_period(self) -> None:
        period_start, period_end = extract_statement_period(
            self.text,
            account=self.account,
        )
        self.assertEqual(period_start, date(2024, 4, 1))
        self.assertEqual(period_end, date(2025, 3, 31))


if __name__ == "__main__":
    _ = unittest.main()
