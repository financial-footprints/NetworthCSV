"""Statement period identifier helpers."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.utils.statement_period import (
    build_calendar_year_sections,
    calendar_bounds_for_period_key,
    covered_months_between,
    email_date_from_staging_filename,
    fiscal_year_key,
    fy_key_from_dates,
    fy_period_bounds,
    is_annual_period,
    is_fy_period,
    period_for_year_key,
    staging_filename_is_annual,
)


class StatementPeriodTests(unittest.TestCase):
    def test_email_date_from_staging_filename(self) -> None:
        self.assertEqual(
            email_date_from_staging_filename("Important__2023-02-18.pdf"),
            date(2023, 2, 18),
        )
        self.assertEqual(
            email_date_from_staging_filename("INBOX__2023-02-15 (1).pdf"),
            date(2023, 2, 15),
        )
        self.assertEqual(
            email_date_from_staging_filename("INBOX__2024-05-12__annual.csv"),
            date(2024, 5, 12),
        )
        self.assertEqual(
            email_date_from_staging_filename("INBOX__2024-05-12.csv"),
            date(2024, 5, 12),
        )
        self.assertIsNone(email_date_from_staging_filename("manual__2023-02.pdf"))
        self.assertIsNone(email_date_from_staging_filename("attachment.pdf"))

    def test_staging_filename_is_annual(self) -> None:
        self.assertTrue(staging_filename_is_annual("INBOX__2024-05-12__annual.csv"))
        self.assertFalse(staging_filename_is_annual("INBOX__2024-05-12.csv"))

    def test_fy_period_round_trip(self) -> None:
        period = "FY24-2025"
        self.assertTrue(is_fy_period(period))
        self.assertTrue(is_annual_period(period))
        self.assertEqual(
            fy_period_bounds(period),
            (date(2024, 4, 1), date(2025, 3, 31)),
        )

    def test_calendar_bounds_for_period_key(self) -> None:
        self.assertEqual(
            calendar_bounds_for_period_key("2026-04"),
            (date(2026, 4, 1), date(2026, 4, 30)),
        )
        self.assertEqual(
            calendar_bounds_for_period_key("FY25-2026"),
            (date(2025, 4, 1), date(2026, 3, 31)),
        )
        self.assertIsNone(calendar_bounds_for_period_key("unknown-month"))

    def test_fiscal_year_key(self) -> None:
        self.assertEqual(
            fiscal_year_key(date(2024, 4, 1), date(2025, 3, 31)),
            "FY24-2025",
        )

    def test_fy_key_from_dates_majority_months(self) -> None:
        cases = [
            ((date(2022, 8, 1), date(2023, 2, 28)), "FY22-2023"),
            ((date(2023, 4, 1), date(2024, 3, 31)), "FY23-2024"),
            ((date(2024, 3, 17), date(2024, 5, 16)), "FY24-2025"),
            ((date(2025, 3, 17), date(2026, 3, 16)), "FY25-2026"),
        ]
        for (start, end), expected in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(fy_key_from_dates(start, end), expected)

    def test_period_for_fiscal_year_key(self) -> None:
        start, end = period_for_year_key("FY24-2025", year_display="fiscal_year")
        self.assertEqual(start, date(2024, 4, 1))
        self.assertEqual(end, date(2025, 3, 31))

    def test_period_for_calendar_year_key(self) -> None:
        start, end = period_for_year_key("2024", year_display="calendar_year")
        self.assertEqual(start, date(2024, 1, 1))
        self.assertEqual(end, date(2024, 12, 31))

    def test_covered_months_between(self) -> None:
        self.assertEqual(
            covered_months_between(date(2024, 4, 1), date(2024, 6, 30)),
            ("2024-04", "2024-05", "2024-06"),
        )

    def test_build_calendar_year_sections_calendar_year(self) -> None:
        sections = build_calendar_year_sections(
            date(2023, 4, 1),
            date(2024, 12, 1),
            year_display="calendar_year",
        )
        self.assertEqual([section.year_key for section in sections], ["2024", "2023"])
        self.assertEqual(len(sections[0].months), 12)
        self.assertEqual(len(sections[1].months), 12)
        self.assertEqual(sections[0].months[0].month_key, "2024-12")
        self.assertEqual(sections[0].months[-1].month_key, "2024-01")
        self.assertEqual(sections[1].months[0].month_key, "2023-12")
        self.assertEqual(sections[1].months[-1].month_key, "2023-01")

    def test_build_calendar_year_sections_fiscal_year(self) -> None:
        sections = build_calendar_year_sections(
            date(2024, 2, 1),
            date(2024, 8, 1),
            year_display="fiscal_year",
        )
        self.assertEqual(
            [section.year_key for section in sections],
            ["FY24-2025", "FY23-2024"],
        )
        self.assertEqual(sections[0].months[0].month_key, "2025-03")
        self.assertEqual(sections[0].months[-1].month_key, "2024-04")
        self.assertEqual(sections[1].months[0].month_key, "2024-03")
        self.assertEqual(sections[1].months[-1].month_key, "2023-04")

    def test_build_calendar_year_sections_fiscal_label(self) -> None:
        sections = build_calendar_year_sections(
            date(2023, 4, 1),
            date(2023, 6, 1),
            year_display="fiscal_year",
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].label, "FY 2023–2024")

    def test_build_calendar_year_sections_invalid_range(self) -> None:
        self.assertEqual(
            build_calendar_year_sections(
                date(2024, 12, 1),
                date(2024, 1, 1),
                year_display="calendar_year",
            ),
            (),
        )


if __name__ == "__main__":
    _ = unittest.main()
