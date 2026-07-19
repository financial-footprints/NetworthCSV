"""Per-period CSV statement preparation orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.pipeline.cleanup.canonical import write_statement_csv
from networthcsv.pipeline.cleanup.exclusion import statement_should_exclude
from networthcsv.pipeline.cleanup.grouping import dedupe_paths_by_hash, file_hash
from networthcsv.pipeline.cleanup.keeper import (
    delete_staging_csv_duplicates_for_month,
    select_csv_keeper,
)
from networthcsv.pipeline.cleanup.period_source import period_source_rank
from networthcsv.pipeline.cleanup.prepare_common import (
    eligible_paths,
    filter_existing,
    load_or_use_raw,
    unlink_excluded,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account import account_label
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks.helpers.text import (
    check_text_contains,
    text_contains_present,
)
from networthcsv.utils.banks.period import PeriodSource
from networthcsv.utils.path import statement_csv_path

logger = logging.getLogger(__name__)


def prepare_csv_month(
    staging_dir: Path,
    download_path: Path,
    month: str,
    candidates: list[Path],
    account: ResolvedAccount,
    *,
    raw_by_path: dict[Path, str] | None = None,
    path_month: dict[Path, str] | None = None,
    path_hash: dict[Path, str] | None = None,
    path_period_source: dict[Path, PeriodSource] | None = None,
    alerts: AlertService | None = None,
) -> tuple[int, int]:
    """Resolve one statement CSV period. Returns (prepared, rejected) counts."""
    existing = filter_existing(candidates)
    if not existing:
        return 0, 0

    unique = dedupe_paths_by_hash(existing, path_hash=path_hash)
    raw_by_path = load_or_use_raw(
        unique,
        raw_by_path,
        lambda path: path.read_text(encoding="utf-8", errors="replace"),
    )
    period_source_lookup = path_period_source or {}
    hash_lookup = path_hash or {}
    label = account_label(account)
    csv_out = statement_csv_path(download_path, account, month)
    text_contains = account.statement.text_contains

    excluded: set[Path] = {
        path
        for path in unique
        if statement_should_exclude(
            raw_by_path[path], raw_by_path[path], account=account, is_manual=False
        )
    }
    unlink_excluded(unique, should_exclude=lambda path: path in excluded)

    eligible = eligible_paths(
        unique,
        is_eligible=lambda path: path not in excluded,
    )
    if not eligible:
        return 0, 1

    keeper, _ = select_csv_keeper(
        eligible,
        raw_by_path=raw_by_path,
        path_period_source=period_source_lookup,
        path_hash=hash_lookup,
        text_contains=text_contains,
    )

    if keeper is None:
        rejected_names = ", ".join(path.name for path in eligible)
        logger.warning(
            "rejected CSV period %s for %s: no keeper "
            "(text_contains not matched in: %s)",
            month,
            label,
            rejected_names,
        )
        for path in eligible:
            if text_contains:
                _ = check_text_contains(
                    raw_by_path[path],
                    text_contains=text_contains,
                    source_file=path.name,
                    account_label=label,
                    alerts=alerts,
                )
        return 0, 1

    keep_digest = hash_lookup.get(keeper) or file_hash(keeper)
    keep_rank = period_source_rank(period_source_lookup.get(keeper, "unknown"))
    for path in eligible:
        if path == keeper:
            continue
        path_digest = hash_lookup.get(path) or file_hash(path)
        path_rank = period_source_rank(period_source_lookup.get(path, "unknown"))
        if path_digest == keep_digest or path_rank > keep_rank:
            if path.is_file():
                _ = path.unlink()
                logger.debug("removed (duplicate csv month): %s", path)
            continue
        if text_contains and not text_contains_present(
            raw_by_path[path], text_contains
        ):
            _ = check_text_contains(
                raw_by_path[path],
                text_contains=text_contains,
                source_file=path.name,
                account_label=label,
                alerts=alerts,
            )

    dedupe_lookup = (
        path_month if path_month is not None else {path: month for path in existing}
    )
    _ = delete_staging_csv_duplicates_for_month(
        staging_dir,
        month,
        dedupe_lookup,
        keep=keeper,
        path_hash=hash_lookup,
        path_period_source=period_source_lookup,
    )

    # Skip rewrite when canonical already matches keeper hash.
    if csv_out.is_file() and file_hash(csv_out) == keep_digest:
        if keeper.resolve() != csv_out.resolve() and keeper.is_file():
            _ = keeper.unlink()
            logger.debug("removed (staging csv, canonical current): %s", keeper)
        return 1, 0

    write_statement_csv(staging_dir, download_path, month, keeper, account)
    return 1, 0
