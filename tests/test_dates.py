"""Date parsing tests."""

from __future__ import annotations

import unittest
from datetime import date

from src.core.dates import parse_date_dmy_mon, parse_date_dmy_mon_short, parse_date_dmy_slash


class DateTests(unittest.TestCase):
    def test_parse_date_dmy_slash(self) -> None:
        self.assertEqual(parse_date_dmy_slash("15/03/2024"), date(2024, 3, 15))
        self.assertIsNone(parse_date_dmy_slash("not-a-date"))

    def test_parse_date_dmy_mon(self) -> None:
        self.assertEqual(parse_date_dmy_mon("15-JAN-2024"), date(2024, 1, 15))
        self.assertEqual(parse_date_dmy_mon("15-jan-2024"), date(2024, 1, 15))
        self.assertIsNone(parse_date_dmy_mon("bad"))

    def test_parse_date_dmy_mon_short(self) -> None:
        self.assertEqual(parse_date_dmy_mon_short("15 Mar 24"), date(2024, 3, 15))
        self.assertIsNone(parse_date_dmy_mon_short("bad"))


if __name__ == "__main__":
    unittest.main()
