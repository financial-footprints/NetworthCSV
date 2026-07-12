"""Credit-card billing periods anchored to account opening date.

Opening date day ``D`` defines recurring cycles:

- ``D == 1``: calendar month (1st through last day of the month).
- ``D > 1``: day ``D`` of month M through day ``D - 1`` of month M+1
  (start day clamped to the month length when needed).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta


def _clamp_day(year: int, month: int, day: int) -> int:
    return min(day, calendar.monthrange(year, month)[1])


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    shifted = month - 1 + delta
    return year + shifted // 12, shifted % 12 + 1


def approximate_period_start_from_statement_end(end: date) -> date:
    """Approximate billing start when only the statement end date is known."""
    prev_year, prev_month = _add_months(end.year, end.month, -1)
    prev_day = _clamp_day(prev_year, prev_month, end.day)
    return date(prev_year, prev_month, prev_day) + timedelta(days=1)


@dataclass(frozen=True, order=True)
class BillingPeriod:
    """One billing cycle window ``[start, end]`` (inclusive)."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(
                f"billing period start {self.start} is after end {self.end}"
            )


class BillingCycle:
    """Recurring billing calendar from an opening-date anchor day."""

    def __init__(self, anchor_day: int) -> None:
        if not 1 <= anchor_day <= 31:
            raise ValueError(f"anchor_day must be 1..31, got {anchor_day}")
        self._anchor_day = anchor_day

    @property
    def anchor_day(self) -> int:
        return self._anchor_day

    @classmethod
    def from_opening_date(cls, opening_date: date) -> BillingCycle:
        return cls(opening_date.day)

    def period_containing(self, txn_date: date) -> BillingPeriod:
        if self._anchor_day == 1:
            last = calendar.monthrange(txn_date.year, txn_date.month)[1]
            return BillingPeriod(
                date(txn_date.year, txn_date.month, 1),
                date(txn_date.year, txn_date.month, last),
            )

        day_in_month = _clamp_day(txn_date.year, txn_date.month, self._anchor_day)
        if txn_date.day >= day_in_month:
            start_year, start_month = txn_date.year, txn_date.month
        else:
            start_year, start_month = _add_months(txn_date.year, txn_date.month, -1)

        start_day = _clamp_day(start_year, start_month, self._anchor_day)
        start = date(start_year, start_month, start_day)
        end_year, end_month = _add_months(start_year, start_month, 1)
        end_day = _clamp_day(end_year, end_month, self._anchor_day - 1)
        return BillingPeriod(start, date(end_year, end_month, end_day))

    def period_start_from_end(self, end: date) -> date:
        """Return period start assuming *end* is the statement period end date."""
        if self._anchor_day == 1:
            return date(end.year, end.month, 1)
        start_year, start_month = _add_months(end.year, end.month, -1)
        start_day = _clamp_day(start_year, start_month, self._anchor_day)
        return date(start_year, start_month, start_day)

    def period_ending_on(self, end: date) -> BillingPeriod:
        return BillingPeriod(self.period_start_from_end(end), end)

    def end_month_key(self, period: BillingPeriod) -> str:
        """Return ``YYYY-MM`` for the month of the period end."""
        return period.end.strftime("%Y-%m")

    def distinct_periods(self, txn_dates: Iterable[date]) -> tuple[BillingPeriod, ...]:
        seen: dict[BillingPeriod, None] = {}
        for txn_date in txn_dates:
            period = self.period_containing(txn_date)
            seen.setdefault(period, None)
        return tuple(seen)

    def bounds_for_transactions(self, txn_dates: Iterable[date]) -> BillingPeriod:
        """Return the span from earliest period start to latest period end."""
        periods = self.distinct_periods(txn_dates)
        if not periods:
            raise ValueError("txn_dates must not be empty")
        return BillingPeriod(
            min(period.start for period in periods),
            max(period.end for period in periods),
        )
