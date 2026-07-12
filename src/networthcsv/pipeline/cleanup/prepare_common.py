"""Shared helpers for per-period statement preparation."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.pipeline.cleanup.keeper import format_ambiguous_candidates
from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks.period import PeriodSource

logger = logging.getLogger(__name__)


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
