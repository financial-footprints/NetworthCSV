"""PNB statement tests using synthetic fixtures."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from networthcsv.pipeline.cleanup.statement_date import resolve_month_stem
from networthcsv.pipeline.metadata.metadata import (
    StatementMetadata,
    compute_balance_gaps,
)
from networthcsv.pipeline.metadata.statement_balance import (
    extract_closing_balance,
    extract_opening_balance,
)
from networthcsv.settings import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ResolvedAccount,
    _resolve_variant_defaults,
)

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pnb" / "platinum"
_APP_CONFIG = AppConfig.from_json(
    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")),
    config_path=DEFAULT_CONFIG_PATH,
)

_STATEMENT_FIXTURES = (
    ("2024-03.txt", "2024-03", "-4200.5", "-2750.5"),
    ("2024-04.txt", "2024-04", "-2750.5", "-1900.0"),
    ("2024-05.txt", "2024-05", "-1900.0", "510.75"),
)

_CHAIN_FIXTURES = (
    ("2024-06.txt", "2024-06", "5000", "1200"),
    ("2024-07.txt", "2024-07", "1200", "800"),
)


def _account(*, variant: str | None = "platinum") -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks["pnb"]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": "pnb",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class PnbStatementFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = _account()

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
                actual_opening = extract_opening_balance(
                    text,
                    tuple(self.account.metadata.balances.opening),
                )
                actual_closing = extract_closing_balance(
                    text,
                    tuple(self.account.metadata.balances.closing),
                )
                self.assertEqual(actual_opening, opening)
                self.assertEqual(actual_closing, closing)


class PnbStatementBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = _account(variant="default")

    def test_integer_account_summary_amounts(self) -> None:
        text = (
            "Account Summary\n"
            "   Previous Balance Purchases and other charges Cash Advances Payments and Other Credits Total Amount Due\n"
            "    -1019       900          0         1000       -1119\n"
        )
        opening = extract_opening_balance(
            text,
            tuple(self.account.metadata.balances.opening),
        )
        self.assertEqual(opening, "-1019")

    def test_mixed_integer_decimal_account_summary_amounts(self) -> None:
        text = (_FIXTURES / "layout_mixed_integer_decimal.txt").read_text(
            encoding="utf-8"
        )
        opening = extract_opening_balance(
            text,
            tuple(self.account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(self.account.metadata.balances.closing),
        )
        self.assertEqual(opening, "-4200.5")
        self.assertEqual(closing, "-2750.5")

    def test_split_closing_header_uses_summary_column_not_payments(self) -> None:
        text = (_FIXTURES / "2024-06.txt").read_text(encoding="utf-8")
        opening = extract_opening_balance(
            text,
            tuple(self.account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(self.account.metadata.balances.closing),
        )
        self.assertEqual(opening, "5000")
        self.assertEqual(closing, "1200")


class PnbStatementDateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = _account()

    def test_same_line_invoice_date(self) -> None:
        text = (_FIXTURES / "layout_same_line_invoice_date.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            resolve_month_stem(text, "attachment.pdf", account=self.account),
            "2024-03",
        )

    def test_garbage_line_invoice_date(self) -> None:
        text = (_FIXTURES / "layout_garbage_line_invoice_date.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            resolve_month_stem(text, "attachment.pdf", account=self.account),
            "2024-02",
        )


if __name__ == "__main__":
    _ = unittest.main()
