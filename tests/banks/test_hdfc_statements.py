"""HDFC statement balance extraction tests."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from networthcsv.pipeline.cleanup.statement_date import (
    extract_statement_date,
    extract_statement_period,
    resolve_statement_period,
)
from networthcsv.pipeline.metadata.metadata import _resolve_statement_period
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler

_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _account(*, variant: str | None) -> ResolvedAccount:
    handler = get_handler("hdfc", variant)
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "hdfc",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class HdfcStatementBalanceTests(unittest.TestCase):
    def test_regalia_split_account_summary_headers(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                      0.00     5.00    12,350.67  0.00    12,345.67\n"
        )
        account = _account(variant="regalia")
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
        account = _account(variant="diners-privilege")
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
        account = _account(variant="diners-privilege")
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
        account = _account(variant="diners-privilege")
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "-4444.44")
        self.assertEqual(closing, "-2222.22")


class HdfcSwiggyCollapsedHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = _account(variant="swiggy")
        cls.text = (
            _FIXTURES_ROOT / "hdfc/swiggy/sample-collapsed-header.txt"
        ).read_text(encoding="utf-8")

    def test_collapsed_header_statement_date(self) -> None:
        parsed = extract_statement_date(self.text, account=self.account)
        self.assertEqual(parsed, date(2024, 6, 20))

    def test_collapsed_header_statement_period_end(self) -> None:
        period_start, period_end = extract_statement_period(
            self.text,
            account=self.account,
        )
        self.assertIsNone(period_start)
        self.assertEqual(period_end, date(2024, 6, 20))

    def test_collapsed_header_resolved_period_bounds(self) -> None:
        period_start, period_end, approximate = _resolve_statement_period(
            self.text,
            account=self.account,
        )
        self.assertEqual(period_start, "21-05-2024")
        self.assertEqual(period_end, "20-06-2024")
        self.assertFalse(approximate)


class HdfcYearlyStatementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = _account(variant="default")
        cls.text = (_FIXTURES_ROOT / "hdfc/default/yearly-sample.txt").read_text(
            encoding="utf-8"
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)

    def test_year_display_is_fiscal(self) -> None:
        self.assertEqual(self.handler.year_display(), "fiscal_year")

    def test_yearly_mail_subjects_merged_in_defaults(self) -> None:
        defaults = self.handler.matching_defaults()
        self.assertIn("Year End Statement Summary", defaults.mail.subjects)

    def test_is_yearly_statement(self) -> None:
        self.assertTrue(self.handler.is_yearly_statement(self.text))

    def test_is_yearly_statement_from_period_pattern_only(self) -> None:
        text = (
            "Account Summary for the period from APRIL-24 to MARCH-25\n"
            "000123456XXXXXX7890"
        )
        self.assertTrue(self.handler.is_yearly_statement(text))

    def test_yearly_period(self) -> None:
        period = self.handler.get_yearly_period(self.text)
        self.assertIsNotNone(period)
        assert period is not None
        self.assertEqual(period[0], date(2024, 4, 1))
        self.assertEqual(period[1], date(2025, 3, 31))

    def test_resolve_yearly_period(self) -> None:
        period = resolve_statement_period(self.text, "sample.pdf", account=self.account)
        self.assertEqual(period, "yearly-2024-04_2025-03")

    def test_yearly_statement_date_is_period_end(self) -> None:
        parsed = extract_statement_date(self.text, account=self.account)
        self.assertEqual(parsed, date(2025, 3, 31))

    def test_yearly_statement_period(self) -> None:
        period_start, period_end = extract_statement_period(
            self.text,
            account=self.account,
        )
        self.assertEqual(period_start, date(2024, 4, 1))
        self.assertEqual(period_end, date(2025, 3, 31))


if __name__ == "__main__":
    _ = unittest.main()
