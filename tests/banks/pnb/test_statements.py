"""PNB statement tests using synthetic fixtures."""

from __future__ import annotations

import unittest
from datetime import date

from cleanup_support import FIXTURES_ROOT, account as make_account
from networthcsv.utils.banks.period import (
    extract_statement_period,
    resolve_period_key,
)
from networthcsv.pipeline.metadata import (
    StatementMetadata,
    compute_balance_gaps,
)
from networthcsv.utils.banks import get_handler

_FIXTURES = FIXTURES_ROOT / "pnb" / "platinum"

_STATEMENT_FIXTURES = (
    ("2024-03.txt", "2024-03", "-4200.5", "-2750.5"),
    ("2024-04.txt", "2024-04", "-2750.5", "-1900.0"),
    ("2024-05.txt", "2024-05", "-1900.0", "510.75"),
)

_CHAIN_FIXTURES = (
    ("2024-06.txt", "2024-06", "5000", "1200"),
    ("2024-07.txt", "2024-07", "1200", "800"),
)


class PnbStatementFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="pnb",
            variant="platinum",
            account_number="1234",
            passwords=["x"],
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)

    def test_statements_have_no_balance_discontinuities(self) -> None:
        statements = tuple(
            StatementMetadata(
                statement_date=statement_month,
                formats=("txt",),
                opening_balance=opening,
                closing_balance=closing,
            )
            for _txt, statement_month, opening, closing in _STATEMENT_FIXTURES
        )
        self.assertEqual(compute_balance_gaps(statements), ())

    def test_chain_statements_have_no_balance_discontinuities(self) -> None:
        statements = tuple(
            StatementMetadata(
                statement_date=statement_month,
                formats=("txt",),
                opening_balance=opening,
                closing_balance=closing,
            )
            for _txt, statement_month, opening, closing in _CHAIN_FIXTURES
        )
        self.assertEqual(compute_balance_gaps(statements), ())

    def test_txt_fixtures_end_at_statement_marker(self) -> None:
        marker = "********** End of Statement **********"
        for txt_name, _month, _opening, _closing in (
            *_STATEMENT_FIXTURES,
            *_CHAIN_FIXTURES,
        ):
            with self.subTest(fixture=txt_name):
                text = (_FIXTURES / txt_name).read_text(encoding="utf-8")
                end_lines = [
                    line for line in text.splitlines() if "End of Statement" in line
                ]
                self.assertEqual(len(end_lines), 1)
                self.assertIn(marker, end_lines[0])
                self.assertEqual(text.splitlines()[-1], end_lines[0])

    def test_txt_fixtures_extract_expected_balances(self) -> None:
        for txt_name, _month, opening, closing in (
            *_STATEMENT_FIXTURES,
            *_CHAIN_FIXTURES,
        ):
            with self.subTest(fixture=txt_name):
                text = (_FIXTURES / txt_name).read_text(encoding="utf-8")
                actual_opening = self.handler.get_opening_balance(text)
                actual_closing = self.handler.get_closing_balance(text)
                self.assertEqual(actual_opening, opening)
                self.assertEqual(actual_closing, closing)


class PnbStatementPeriodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="pnb",
            variant="platinum",
            account_number="1234",
            passwords=["x"],
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)

    def test_fixture_extracts_statement_period_bounds(self) -> None:
        cases = (
            ("sample.txt", date(2021, 4, 17), date(2021, 5, 16)),
            ("2024-03.txt", date(2024, 2, 17), date(2024, 3, 16)),
            ("2024-04.txt", date(2024, 3, 17), date(2024, 4, 16)),
            ("2024-05.txt", date(2024, 4, 17), date(2024, 5, 16)),
            ("2024-06.txt", date(2024, 5, 17), date(2024, 6, 16)),
            ("2024-07.txt", date(2024, 6, 17), date(2024, 7, 16)),
        )
        for txt_name, expected_start, expected_end in cases:
            with self.subTest(fixture=txt_name):
                text = (_FIXTURES / txt_name).read_text(encoding="utf-8")
                period_start, period_end = self.handler.get_statement_period(text)
                self.assertEqual(period_start, expected_start)
                self.assertEqual(period_end, expected_end)

    def test_spaced_period_end_day_fixture(self) -> None:
        text = (_FIXTURES / "layout_spaced_period_end_day.txt").read_text(
            encoding="utf-8"
        )
        period_start, period_end = self.handler.get_statement_period(text)
        self.assertEqual(period_start, date(2024, 2, 17))
        self.assertEqual(period_end, date(2024, 3, 16))
        self.assertEqual(self.handler.get_statement_date(text), date(2024, 3, 16))

    def test_extract_statement_period_via_pipeline(self) -> None:
        text = (_FIXTURES / "2024-03.txt").read_text(encoding="utf-8")
        period_start, period_end = extract_statement_period(text, account=self.account)
        self.assertEqual(period_start, date(2024, 2, 17))
        self.assertEqual(period_end, date(2024, 3, 16))


class PnbStatementBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="pnb",
            variant="default",
            account_number="1234",
            passwords=["x"],
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)

    def test_integer_account_summary_amounts(self) -> None:
        text = (
            "Account Summary\n"
            "   Previous Balance Purchases and other charges Cash Advances Payments and Other Credits Total Amount Due\n"
            "    -1019       900          0         1000       -1119\n"
        )
        opening = self.handler.get_opening_balance(text)
        self.assertEqual(opening, "-1019")

    def test_mixed_integer_decimal_account_summary_amounts(self) -> None:
        text = (_FIXTURES / "layout_mixed_integer_decimal.txt").read_text(
            encoding="utf-8"
        )
        opening = self.handler.get_opening_balance(text)
        closing = self.handler.get_closing_balance(text)
        self.assertEqual(opening, "-4200.5")
        self.assertEqual(closing, "-2750.5")

    def test_split_closing_header_uses_summary_column_not_payments(self) -> None:
        text = (_FIXTURES / "2024-06.txt").read_text(encoding="utf-8")
        opening = self.handler.get_opening_balance(text)
        closing = self.handler.get_closing_balance(text)
        self.assertEqual(opening, "5000")
        self.assertEqual(closing, "1200")


class PnbStatementDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="pnb",
            variant="platinum",
            account_number="1234",
            passwords=["x"],
        )

    def test_same_line_invoice_date(self) -> None:
        text = (_FIXTURES / "layout_same_line_invoice_date.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            resolve_period_key(text, "attachment.pdf", account=self.account),
            "2024-03",
        )

    def test_garbage_line_invoice_date(self) -> None:
        text = (_FIXTURES / "layout_garbage_line_invoice_date.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            resolve_period_key(text, "attachment.pdf", account=self.account),
            "2024-02",
        )


class PnbMarketingPrefixLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="pnb",
            variant="platinum",
            account_number="1234",
            passwords=["x"],
        )
        cls.handler = get_handler(cls.account.bank, cls.account.variant)
        cls.text = (_FIXTURES / "layout_marketing_prefix.txt").read_text(
            encoding="utf-8"
        )

    def test_marketing_prefix_month_from_invoice_date(self) -> None:
        self.assertEqual(
            resolve_period_key(
                self.text,
                "All Mail__2024-03-19.pdf",
                account=self.account,
            ),
            "2024-03",
        )

    def test_marketing_prefix_statement_date(self) -> None:
        self.assertEqual(self.handler.get_statement_date(self.text), date(2024, 3, 16))

    def test_marketing_prefix_statement_period_bounds(self) -> None:
        period_start, period_end = self.handler.get_statement_period(self.text)
        self.assertEqual(period_start, date(2024, 2, 17))
        self.assertEqual(period_end, date(2024, 3, 16))

    def test_marketing_prefix_closing_balance(self) -> None:
        self.assertEqual(self.handler.get_closing_balance(self.text), "250")

    def test_marketing_prefix_clean_text_retains_card_marker(self) -> None:
        cleaned = self.handler.clean_text(self.text)
        self.assertIn("441299XXXXXX5678", cleaned)
        self.assertNotIn("Presenting Rupay Platinum", cleaned)


class PnbInvoiceReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = get_handler("pnb", "platinum")

    def test_v1_fixture_invoice_reference(self) -> None:
        text = (_FIXTURES / "2024-03.txt").read_text(encoding="utf-8")
        self.assertEqual(self.handler.get_statement_reference(text), "2024CC0100456")

    def test_v2_marketing_fixture_invoice_reference(self) -> None:
        text = (_FIXTURES / "layout_marketing_prefix.txt").read_text(encoding="utf-8")
        self.assertEqual(self.handler.get_statement_reference(text), "2024CC0100999")


if __name__ == "__main__":
    _ = unittest.main()
