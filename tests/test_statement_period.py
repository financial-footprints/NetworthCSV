"""Statement period identifier helpers."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.utils.statement_period import (
    fiscal_year_key,
    is_yearly_period,
    period_for_year_key,
    yearly_period_for_year_key,
    yearly_period_from_dates,
)


class StatementPeriodTests(unittest.TestCase):
    def test_yearly_period_round_trip(self) -> None:
        period = yearly_period_from_dates(date(2024, 4, 1), date(2025, 3, 31))
        self.assertEqual(period, "yearly-2024-04_2025-03")
        self.assertTrue(is_yearly_period(period))

    def test_fiscal_year_key(self) -> None:
        self.assertEqual(
            fiscal_year_key(date(2024, 4, 1), date(2025, 3, 31)),
            "FY24-2025",
        )

    def test_yearly_period_for_fiscal_year_key(self) -> None:
        period = yearly_period_for_year_key("FY24-2025", year_display="fiscal_year")
        self.assertEqual(period, "yearly-2024-04_2025-03")

    def test_period_for_calendar_year_key(self) -> None:
        start, end = period_for_year_key("2024", year_display="calendar_year")
        self.assertEqual(start, date(2024, 1, 1))
        self.assertEqual(end, date(2024, 12, 31))

    def test_build_calendar_year_sections_fiscal(self) -> None:
        from networthcsv.utils.statement_period import build_calendar_year_sections

        sections = build_calendar_year_sections(
            date(2024, 4, 1),
            date(2025, 3, 31),
            year_display="fiscal_year",
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].year_key, "FY24-2025")
        self.assertEqual(sections[0].label, "FY 2024–2025")
        self.assertEqual(sections[0].months[0].month_key, "2025-03")


if __name__ == "__main__":
    _ = unittest.main()
