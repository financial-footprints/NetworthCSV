"""BillingCycle / BillingPeriod unit tests."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.utils.billing_period import BillingCycle, BillingPeriod


class BillingCycleExamplesTests(unittest.TestCase):
    def test_example_anchor_day_17(self) -> None:
        cycle = BillingCycle(17)
        self.assertEqual(
            cycle.period_containing(date(2023, 5, 17)),
            BillingPeriod(date(2023, 5, 17), date(2023, 6, 16)),
        )
        self.assertEqual(
            cycle.period_containing(date(2023, 4, 17)),
            BillingPeriod(date(2023, 4, 17), date(2023, 5, 16)),
        )
        self.assertEqual(
            cycle.period_containing(date(2023, 3, 17)),
            BillingPeriod(date(2023, 3, 17), date(2023, 4, 16)),
        )
        self.assertEqual(
            cycle.period_containing(date(2023, 2, 20)),
            BillingPeriod(date(2023, 2, 17), date(2023, 3, 16)),
        )
        self.assertEqual(
            cycle.period_containing(date(2023, 3, 16)),
            BillingPeriod(date(2023, 2, 17), date(2023, 3, 16)),
        )

    def test_example_anchor_day_1_calendar_months(self) -> None:
        cycle = BillingCycle(1)
        self.assertEqual(
            cycle.period_containing(date(2001, 1, 1)),
            BillingPeriod(date(2001, 1, 1), date(2001, 1, 31)),
        )
        self.assertEqual(
            cycle.period_containing(date(2001, 1, 15)),
            BillingPeriod(date(2001, 1, 1), date(2001, 1, 31)),
        )
        self.assertEqual(
            cycle.period_containing(date(2001, 2, 1)),
            BillingPeriod(date(2001, 2, 1), date(2001, 2, 28)),
        )
        self.assertEqual(
            cycle.period_containing(date(2001, 2, 28)),
            BillingPeriod(date(2001, 2, 1), date(2001, 2, 28)),
        )
        self.assertEqual(
            cycle.period_containing(date(2001, 3, 10)),
            BillingPeriod(date(2001, 3, 1), date(2001, 3, 31)),
        )
        self.assertEqual(
            cycle.period_containing(date(2001, 4, 1)),
            BillingPeriod(date(2001, 4, 1), date(2001, 4, 30)),
        )

    def test_example_anchor_day_9(self) -> None:
        cycle = BillingCycle(9)
        self.assertEqual(
            cycle.period_containing(date(2026, 9, 9)),
            BillingPeriod(date(2026, 9, 9), date(2026, 10, 8)),
        )
        self.assertEqual(
            cycle.period_containing(date(2026, 8, 9)),
            BillingPeriod(date(2026, 8, 9), date(2026, 9, 8)),
        )
        self.assertEqual(
            cycle.period_containing(date(2026, 7, 9)),
            BillingPeriod(date(2026, 7, 9), date(2026, 8, 8)),
        )
        self.assertEqual(
            cycle.period_containing(date(2026, 6, 15)),
            BillingPeriod(date(2026, 6, 9), date(2026, 7, 8)),
        )


class BillingCycleEdgeTests(unittest.TestCase):
    def test_from_opening_date(self) -> None:
        cycle = BillingCycle.from_opening_date(date(2023, 5, 17))
        self.assertEqual(cycle.anchor_day, 17)

    def test_invalid_anchor_day(self) -> None:
        with self.assertRaises(ValueError):
            _ = BillingCycle(0)
        with self.assertRaises(ValueError):
            _ = BillingCycle(32)

    def test_anchor_day_1_period_start_from_end(self) -> None:
        cycle = BillingCycle(1)
        self.assertEqual(
            cycle.period_start_from_end(date(2025, 1, 31)), date(2025, 1, 1)
        )

    def test_anchor_day_31_clamped_in_short_month(self) -> None:
        cycle = BillingCycle(31)
        # Feb 2024 is a leap year (29 days); period starting Jan 31 ends Feb 29.
        period = cycle.period_containing(date(2024, 2, 15))
        self.assertEqual(period.start, date(2024, 1, 31))
        self.assertEqual(period.end, date(2024, 2, 29))
        # Non-leap Feb 2025.
        period = cycle.period_containing(date(2025, 2, 10))
        self.assertEqual(period.start, date(2025, 1, 31))
        self.assertEqual(period.end, date(2025, 2, 28))

    def test_period_start_from_end_anchor_17(self) -> None:
        cycle = BillingCycle(17)
        self.assertEqual(
            cycle.period_start_from_end(date(2023, 6, 16)),
            date(2023, 5, 17),
        )

    def test_anchor_day_1_end_of_january_start_is_first(self) -> None:
        cycle = BillingCycle(1)
        period = cycle.period_ending_on(date(2025, 1, 31))
        self.assertEqual(period.start, date(2025, 1, 1))
        self.assertEqual(period.end, date(2025, 1, 31))

    def test_end_month_key(self) -> None:
        cycle = BillingCycle(17)
        period = BillingPeriod(date(2023, 5, 17), date(2023, 6, 16))
        self.assertEqual(cycle.end_month_key(period), "2023-06")

    def test_distinct_periods_same_cycle(self) -> None:
        cycle = BillingCycle(17)
        periods = cycle.distinct_periods(
            [date(2023, 5, 20), date(2023, 6, 1), date(2023, 6, 16)]
        )
        self.assertEqual(len(periods), 1)

    def test_distinct_periods_adjacent_cycles(self) -> None:
        cycle = BillingCycle(17)
        periods = cycle.distinct_periods([date(2023, 5, 20), date(2023, 6, 17)])
        self.assertEqual(len(periods), 2)

    def test_bounds_for_transactions(self) -> None:
        cycle = BillingCycle(17)
        bounds = cycle.bounds_for_transactions([date(2023, 5, 20), date(2023, 6, 20)])
        self.assertEqual(bounds.start, date(2023, 5, 17))
        self.assertEqual(bounds.end, date(2023, 7, 16))

    def test_bounds_for_transactions_empty(self) -> None:
        cycle = BillingCycle(17)
        with self.assertRaises(ValueError):
            _ = cycle.bounds_for_transactions([])

    def test_billing_period_rejects_inverted_range(self) -> None:
        with self.assertRaises(ValueError):
            _ = BillingPeriod(date(2023, 6, 1), date(2023, 5, 1))


if __name__ == "__main__":
    _ = unittest.main()
