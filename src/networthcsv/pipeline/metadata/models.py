"""Metadata stage dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StatementGranularity = Literal["monthly", "annual"]
BalanceGapStatus = Literal["matched", "mismatched", "discontinuity"]


@dataclass(frozen=True)
class StatementMetadata:
    statement_date: str
    formats: tuple[str, ...]
    opening_balance: str | None = None
    closing_balance: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    period_approximate: bool = False
    granularity: StatementGranularity = "monthly"
    covered_months: tuple[str, ...] = ()
    year_key: str | None = None


@dataclass(frozen=True)
class AnnualStatementSummary:
    year_key: str
    statement_date: str
    label: str
    period_start: str
    period_end: str
    formats: tuple[str, ...]


@dataclass(frozen=True)
class CoverageSegment:
    start: str
    end: str
    approximate: bool = False


@dataclass(frozen=True)
class CoverageGap:
    start: str
    end: str
    balances_match: bool | None = None


@dataclass(frozen=True)
class PeriodCovered:
    start: str | None
    end: str | None
    segments: tuple[CoverageSegment, ...]
    gaps: tuple[CoverageGap, ...]
    months: tuple[str, ...]
    approximate_statement_count: int = 0


@dataclass(frozen=True)
class BalanceGap:
    month: str
    status: BalanceGapStatus


@dataclass(frozen=True)
class AccountMetadata:
    account_number: str
    bank: str
    variant: str | None
    account_type: str
    opening_date: str | None
    closing_date: str | None
    formats: tuple[str, ...]
    statements: tuple[StatementMetadata, ...]
    statement_dates: tuple[str, ...]
    starting: str | None
    ending: str | None
    statement_count: int
    period_covered: PeriodCovered
    last_fetch_date: str | None = None
