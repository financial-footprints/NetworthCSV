"""Tests for opening/closing balance extraction from statement text."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from networthcsv.pipeline.metadata.statement_balance import (
    balances_match,
    extract_closing_balance,
    extract_opening_balance,
    parse_amount_string,
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


def _account(*, bank: str, variant: str | None) -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks[bank]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class ParseAmountStringTests(unittest.TestCase):
    def test_plain_decimal(self) -> None:
        self.assertEqual(parse_amount_string("1,234.56"), "1234.56")

    def test_credit_suffix(self) -> None:
        self.assertEqual(parse_amount_string("Rs. 91.68 Cr"), "-91.68")

    def test_debit_suffix(self) -> None:
        self.assertEqual(parse_amount_string("1180.00 DR"), "1180.00")

    def test_r_prefix(self) -> None:
        self.assertEqual(parse_amount_string("r501.00 CR"), "-501.00")

    def test_c_prefix(self) -> None:
        self.assertEqual(parse_amount_string("C1,234.56"), "1234.56")

    def test_negative(self) -> None:
        self.assertEqual(parse_amount_string("-1119"), "-1119")

    def test_negative_decimal_preserves_sign(self) -> None:
        self.assertEqual(parse_amount_string("-555.55"), "-555.55")

    def test_dot_zero(self) -> None:
        self.assertEqual(parse_amount_string(".00"), "0.00")


class BalancesMatchTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(balances_match("10.00", "10.00"))

    def test_small_diff_within_default_tolerance(self) -> None:
        self.assertTrue(balances_match("1111.00", "1111.01"))

    def test_boundary_default_tolerance(self) -> None:
        self.assertTrue(balances_match("1111.00", "1111.21"))

    def test_diff_above_default_tolerance(self) -> None:
        self.assertFalse(balances_match("1111.00", "1111.22"))

    def test_custom_tolerance(self) -> None:
        self.assertTrue(balances_match("1111.00", "1111.02", tolerance=Decimal("0.02")))
        self.assertFalse(
            balances_match("1111.00", "1111.03", tolerance=Decimal("0.02"))
        )


class ExtractBalanceSnippetTests(unittest.TestCase):
    def test_bob_account_summary_table(self) -> None:
        text = (
            "Account Summary\n"
            "                                (cid:28)                  / (cid:20)          N   e    w /          (cid:34)\n"
            "Opening Balance Payment/Credits        Closing Balance\n"
            "                               Purchases/Debits\n"
            "    .00        1,001.00      10.00        -991.00\n"
            "Bonus/Reward Points Summary\n"
            "Opening Balance Earned    Redeemed/Expired Closing Balance\n"
            "    0             0            0            0\n"
        )
        account = _account(bank="bob", variant="easy")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-991.00")

    def test_indusind_previous_balance_next_line(self) -> None:
        text = "Previous Balance\n0.00 DR\nTotal Amount Due\n990.00 CR\n"
        account = _account(bank="indusind", variant="default")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-990.00")

    def test_csb_edge_summary_skips_payment_due_row(self) -> None:
        text = (
            "     Rs. 3,457.05                         01 May  2026\n"
            "     Rs. 500.00                           17/04/2026\n"
            "                     22/03/2026                                         Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
        )
        account = _account(bank="csb", variant="edge")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        self.assertEqual(opening, "0.00")

    def test_hdfc_split_account_summary_headers(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                      0.00     5.00    12,350.67  0.00    12,345.67\n"
        )
        account = _account(bank="hdfc", variant="regalia")
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

    def test_hdfc_diners_account_summary_with_credit_closing(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     11,111.11 11,211.11 0.00     0.00     -555.55\n"
        )
        account = _account(bank="hdfc", variant="diners")
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

    def test_hdfc_diners_account_summary_mixed_signs(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     -2,222.22 0.00    13,333.33  0.00    11,111.11\n"
        )
        account = _account(bank="hdfc", variant="diners")
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

    def test_hdfc_diners_negative_opening_and_closing(self) -> None:
        text = (
            "Account Summary\n"
            "                                    Opening  Payment/  Purchase/ Finance\n"
            "                                                                         Total Dues\n"
            "                                    Balance   Credits   Debits   Charges\n"
            "                                     -4,444.44 0.00     2,222.22  0.00    -2,222.22\n"
        )
        account = _account(bank="hdfc", variant="diners")
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

    def test_pnb_integer_account_summary_amounts(self) -> None:
        text = (
            "Account Summary\n"
            "   Previous Balance Purchases and other charges Cash Advances Payments and Other Credits Total Amount Due\n"
            "    -1019       900          0         1000       -1119\n"
        )
        account = _account(bank="pnb", variant="default")
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        self.assertEqual(opening, "-1019")


if __name__ == "__main__":
    _ = unittest.main()
