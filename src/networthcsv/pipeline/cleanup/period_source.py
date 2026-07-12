"""Period source ranking for keeper selection."""

from __future__ import annotations

from pathlib import Path

from networthcsv.pipeline.upload import period_from_manual_upload
from networthcsv.utils.banks.period import PeriodSource

_PERIOD_SOURCE_RANK: dict[PeriodSource, int] = {
    "manual": -1,
    "yearly": 0,
    "content_date": 1,
    "filename_fallback": 2,
    "unknown": 3,
}


def period_source_rank(source: PeriodSource) -> int:
    return _PERIOD_SOURCE_RANK[source]


def period_source_for_path(
    path: Path,
    lookup: dict[Path, PeriodSource],
) -> PeriodSource:
    source = lookup.get(path)
    if source is not None:
        return source
    if period_from_manual_upload(path.name):
        return "manual"
    return "unknown"
