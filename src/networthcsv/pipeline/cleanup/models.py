"""Shared cleanup stage dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from networthcsv.utils.banks.period import PeriodSource


@dataclass(frozen=True)
class MonthGroups:
    groups: dict[str, list[Path]]
    raw_by_path: dict[Path, str]
    path_month: dict[Path, str]
    path_hash: dict[Path, str]
    path_period_source: dict[Path, PeriodSource]
