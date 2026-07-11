"""HDFC statement balance extraction tests."""

from __future__ import annotations

import json
import unittest

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

_APP_CONFIG = AppConfig.from_json(
    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")),
    config_path=DEFAULT_CONFIG_PATH,
)


def _account(*, variant: str | None) -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks["hdfc"]
    defaults = _resolve_variant_defaults(bank_variants, variant)
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
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
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
        account = _account(variant="diners")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
        self.assertEqual(opening, "11111.11")
        self.assertEqual(closing, "-555.55")
        self.assertEqual(len(account.metadata.balances.opening), 2)
        self.assertEqual(len(account.metadata.balances.closing), 2)

    def test_diners_account_summary_mixed_signs(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     -2,222.22 0.00    13,333.33  0.00    11,111.11\n"
        )
        account = _account(variant="diners")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
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
        account = _account(variant="diners")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
        self.assertEqual(opening, "-4444.44")
        self.assertEqual(closing, "-2222.22")


if __name__ == "__main__":
    _ = unittest.main()
