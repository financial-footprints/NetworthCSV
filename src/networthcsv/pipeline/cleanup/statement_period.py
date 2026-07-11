"""Derive statement period boundaries from bank billing rules."""

from __future__ import annotations

import calendar
from datetime import date


def period_start_from_end(end: date, start_day: int) -> date:
    """Return period start on start_day of the month before end's month."""
    if end.month == 1:
        prev_year = end.year - 1
        prev_month = 12
    else:
        prev_year = end.year
        prev_month = end.month - 1
    last_day = calendar.monthrange(prev_year, prev_month)[1]
    day = min(start_day, last_day)
    return date(prev_year, prev_month, day)
