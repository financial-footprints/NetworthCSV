"""Statement coverage and balance gap computation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from networthcsv.pipeline.metadata.models import (
    BalanceGap,
    BalanceGapStatus,
    CoverageGap,
    CoverageSegment,
    PeriodCovered,
    StatementMetadata,
)
from networthcsv.utils.account_dates import parse_account_date, require_account_date_str
from networthcsv.utils.banks.helpers.amounts import balances_match
from networthcsv.utils.statement_period import (
    is_annual_period,
    is_fy_period,
    period_for_year_key,
)


def covered_month(statement_date: str) -> str:
    if is_annual_period(statement_date):
        if is_fy_period(statement_date):
            year_display = "fiscal_year"
        else:
            year_display = "calendar_year"
        start, _end = period_for_year_key(
            statement_date,
            year_display=year_display,
        )
        return start.strftime("%Y-%m")
    year_str, month_str = statement_date.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def statement_date_for_covered_month(covered: str) -> str:
    return next_month_key(covered)


def next_month_key(month: str) -> str:
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    month_num = int(month_str)
    if month_num == 12:
        return f"{year + 1}-01"
    return f"{year}-{month_num + 1:02d}"


def months_between_exclusive(start: str, end: str) -> tuple[str, ...]:
    """Return YYYY-MM covered-month keys strictly between start and end."""
    if start >= end:
        return ()
    months: list[str] = []
    current = next_month_key(start)
    while current < end:
        months.append(current)
        current = next_month_key(current)
    return tuple(months)


def compute_balance_gaps(
    statements: tuple[StatementMetadata, ...],
    *,
    tolerance: Decimal | None = None,
) -> tuple[BalanceGap, ...]:
    """Mark gap months and adjacent-statement balance discontinuities."""
    annual_covered: set[str] = set()
    for statement in statements:
        if statement.granularity == "annual":
            annual_covered.update(statement.covered_months)

    monthly_statements = tuple(
        statement for statement in statements if statement.granularity == "monthly"
    )
    if len(monthly_statements) < 2:
        return ()

    sorted_statements = sorted(
        monthly_statements,
        key=lambda item: covered_month(item.statement_date),
    )
    gaps: list[BalanceGap] = []
    for index in range(len(sorted_statements) - 1):
        previous = sorted_statements[index]
        following = sorted_statements[index + 1]
        previous_covered = covered_month(previous.statement_date)
        following_covered = covered_month(following.statement_date)
        between = months_between_exclusive(previous_covered, following_covered)

        closing = previous.closing_balance
        opening = following.opening_balance
        if closing is None or opening is None:
            continue

        if between:
            status: BalanceGapStatus = (
                "matched"
                if balances_match(closing, opening, tolerance=tolerance)
                else "mismatched"
            )
            gaps.extend(
                BalanceGap(month=month, status=status)
                for month in between
                if month not in annual_covered
            )
            continue

        if following_covered == next_month_key(previous_covered) and not balances_match(
            closing, opening, tolerance=tolerance
        ):
            gaps.append(BalanceGap(month=previous_covered, status="discontinuity"))
            gaps.append(BalanceGap(month=following_covered, status="discontinuity"))

    return tuple(gaps)


def parse_account_date_value(value: str) -> date:
    parsed = parse_account_date(value, "date")
    if parsed is None:
        raise ValueError(f"invalid account date: {value!r}")
    return parsed


def merge_coverage_periods(
    periods: list[tuple[date, date, bool]],
) -> tuple[list[tuple[date, date, bool]], list[tuple[date, date]]]:
    if not periods:
        return [], []
    sorted_periods = sorted(periods, key=lambda item: item[0])
    segments: list[tuple[date, date, bool]] = []
    gaps: list[tuple[date, date]] = []
    current_start, current_end, current_approximate = sorted_periods[0]
    for start, end, approximate in sorted_periods[1:]:
        if start <= current_end + timedelta(days=1):
            if end > current_end:
                current_end = end
            current_approximate = current_approximate or approximate
            continue
        segments.append((current_start, current_end, current_approximate))
        gap_start = current_end + timedelta(days=1)
        gap_end = start - timedelta(days=1)
        if gap_start <= gap_end:
            gaps.append((gap_start, gap_end))
        current_start, current_end, current_approximate = start, end, approximate
    segments.append((current_start, current_end, current_approximate))
    return segments, gaps


def coverage_gap_balances_match(
    statements: tuple[StatementMetadata, ...],
    *,
    segment_before_end: str,
    segment_after_start: str,
    tolerance: Decimal | None,
) -> bool | None:
    """Compare monthly balances across a day-range gap."""
    monthly = tuple(
        statement for statement in statements if statement.granularity == "monthly"
    )
    previous = next(
        (
            statement
            for statement in monthly
            if statement.period_end == segment_before_end
        ),
        None,
    )
    after_start = parse_account_date_value(segment_after_start)
    following_match = min(
        (
            (parse_account_date_value(start), statement)
            for statement in monthly
            if (start := statement.period_start) is not None
            and parse_account_date_value(start) >= after_start
        ),
        key=lambda item: item[0],
        default=None,
    )
    following = None if following_match is None else following_match[1]
    if previous is None or following is None:
        return None
    closing = previous.closing_balance
    opening = following.opening_balance
    if closing is None or opening is None:
        return None
    return balances_match(closing, opening, tolerance=tolerance)


def build_period_covered(
    statements: tuple[StatementMetadata, ...],
    *,
    tolerance: Decimal | None = None,
) -> PeriodCovered:
    months = tuple(
        sorted(
            {
                *(
                    covered_month(statement.statement_date)
                    for statement in statements
                    if statement.granularity == "monthly"
                ),
                *(
                    month
                    for statement in statements
                    if statement.granularity == "annual"
                    for month in statement.covered_months
                ),
            }
        )
    )
    periods: list[tuple[date, date, bool]] = []
    approximate_statement_count = 0
    for statement in statements:
        if statement.period_approximate:
            approximate_statement_count += 1
        if statement.period_start is None or statement.period_end is None:
            continue
        periods.append(
            (
                parse_account_date_value(statement.period_start),
                parse_account_date_value(statement.period_end),
                statement.period_approximate,
            )
        )
    if not periods:
        return PeriodCovered(
            start=None,
            end=None,
            segments=(),
            gaps=(),
            months=months,
            approximate_statement_count=approximate_statement_count,
        )
    merged_segments, merged_gaps = merge_coverage_periods(periods)
    segments = tuple(
        CoverageSegment(
            start=require_account_date_str(start),
            end=require_account_date_str(end),
            approximate=approximate,
        )
        for start, end, approximate in merged_segments
    )
    gaps = tuple(
        CoverageGap(
            start=require_account_date_str(start),
            end=require_account_date_str(end),
            balances_match=coverage_gap_balances_match(
                statements,
                segment_before_end=require_account_date_str(merged_segments[index][1]),
                segment_after_start=require_account_date_str(
                    merged_segments[index + 1][0]
                ),
                tolerance=tolerance,
            ),
        )
        for index, (start, end) in enumerate(merged_gaps)
    )
    return PeriodCovered(
        start=segments[0].start,
        end=segments[-1].end,
        segments=segments,
        gaps=gaps,
        months=months,
        approximate_statement_count=approximate_statement_count,
    )
