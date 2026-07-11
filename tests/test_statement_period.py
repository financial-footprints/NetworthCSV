"""Tests for statement period derivation from bank billing rules."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.pipeline.cleanup.statement_period import period_start_from_end


class PeriodStartFromEndTests(unittest.TestCase):
    def test_hdfc_style_prior_month(self) -> None:
        self.assertEqual(
            period_start_from_end(date(2021, 9, 20), 21),
            date(2021, 8, 21),
        )

    def test_january_rolls_to_december(self) -> None:
        self.assertEqual(
            period_start_from_end(date(2024, 1, 20), 21),
            date(2023, 12, 21),
        )

    def test_start_day_clamped_to_month_length(self) -> None:
        self.assertEqual(
            period_start_from_end(date(2021, 3, 20), 31),
            date(2021, 2, 28),
        )


if __name__ == "__main__":
    _ = unittest.main()
