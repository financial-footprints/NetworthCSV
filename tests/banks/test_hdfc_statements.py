"""HDFC statement balance extraction tests."""

from __future__ import annotations

import unittest

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler


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


if __name__ == "__main__":
    _ = unittest.main()
