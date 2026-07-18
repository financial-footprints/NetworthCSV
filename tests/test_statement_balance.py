"""Tests for opening/closing balance extraction from statement text."""

from __future__ import annotations

import unittest
from decimal import Decimal

from networthcsv.utils.banks.helpers.amounts import (
    balances_match,
    parse_amount_string,
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

    def test_c_prefix_negative_with_comma_after_sign(self) -> None:
        self.assertEqual(parse_amount_string("C-,137.30"), "-137.30")

    def test_c_prefix_positive_decimal(self) -> None:
        self.assertEqual(parse_amount_string("C276.90"), "276.90")

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


if __name__ == "__main__":
    _ = unittest.main()
