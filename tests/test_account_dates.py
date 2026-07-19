"""Tests for account config date parsing and formatting."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.utils.account_dates import (
    format_account_date,
    parse_opening_date,
    require_account_date_str,
)


class AccountDatesTests(unittest.TestCase):
    def test_format_account_date_always_uses_four_digit_year(self) -> None:
        self.assertEqual(format_account_date(date(154, 3, 3)), "03-03-0154")
        self.assertEqual(require_account_date_str(date(145, 3, 31)), "31-03-0145")

    def test_parse_opening_date_round_trips_formatted_values(self) -> None:
        formatted = require_account_date_str(date(2001, 2, 3))
        self.assertEqual(parse_opening_date(formatted), date(2001, 2, 3))

    def test_parse_opening_date_rejects_dates_before_1970(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_opening_date("31-12-1969")

    def test_parse_opening_date_accepts_1970_01_01(self) -> None:
        self.assertEqual(parse_opening_date("01-01-1970"), date(1970, 1, 1))

    def test_parse_opening_date_rejects_dates_after_current_year(self) -> None:
        future_year = date.today().year + 1
        with self.assertRaises(ValueError):
            _ = parse_opening_date(f"01-01-{future_year}")


if __name__ == "__main__":
    unittest.main()
