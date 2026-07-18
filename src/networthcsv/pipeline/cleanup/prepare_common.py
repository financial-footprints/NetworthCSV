"""Shared helpers for per-period statement preparation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from networthcsv.pipeline.cleanup.keeper import format_ambiguous_candidates
from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks.period import PeriodSource

logger = logging.getLogger(__name__)


def filter_existing(candidates: list[Path]) -> list[Path]:
    return [path for path in candidates if path.is_file()]


def load_or_use_raw(
    unique: list[Path],
    raw_by_path: dict[Path, str] | None,
    loader: Callable[[Path], str],
) -> dict[Path, str]:
    if raw_by_path is not None:
        return raw_by_path
    return {path: loader(path) for path in unique}


def unlink_excluded(
    unique: list[Path],
    *,
    should_exclude: Callable[[Path], bool],
    log_label: str = "excluded statement",
) -> None:
    for path in unique:
        if not should_exclude(path):
            continue
        if path.is_file():
            _ = path.unlink()
            logger.debug("removed (%s): %s", log_label, path)


def eligible_paths(
    unique: list[Path],
    *,
    is_eligible: Callable[[Path], bool],
) -> list[Path]:
    return [path for path in unique if path.is_file() and is_eligible(path)]


def report_ambiguous_period(
    *,
    format_label: str,
    label: str,
    month: str,
    ambiguous_paths: list[Path],
    period_source_lookup: dict[Path, PeriodSource],
    text_contains: list[str],
    alerts: AlertService | None,
) -> None:
    conflict_summary = format_ambiguous_candidates(
        ambiguous_paths,
        period_source_lookup,
    )
    logger.warning(
        "ambiguous %s statement period for %s: %s for month %s; "
        "leaving files in staging",
        format_label,
        label,
        conflict_summary,
        month,
    )
    if alerts is None:
        return
    alerts.emit(
        Alert(
            kind=AlertKind.AMBIGUOUS_STATEMENT_PERIOD,
            message=(
                f"multiple matching {format_label}s with same period confidence "
                f"for {month}: {conflict_summary}; manual review required"
            ),
            account=label,
            source_file=month,
            text_contains=list(text_contains),
        )
    )
