"""Duplicate PDF resolution and keeper selection."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.pipeline.cleanup.grouping import file_hash
from networthcsv.pipeline.cleanup.period_source import (
    period_source_for_path,
    period_source_rank,
)
from networthcsv.pipeline.cleanup.staging import is_staging_pdf
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.text import text_contains_present
from networthcsv.utils.banks.period import PeriodSource
from networthcsv.utils.path import iter_pdfs
from networthcsv.utils.statement_period import email_date_from_staging_filename

logger = logging.getLogger(__name__)


def statement_identity_key(
    text: str,
    account: ResolvedAccount,
) -> tuple[object, ...]:
    handler = get_handler(account.bank, account.variant)
    period_start, period_end = handler.get_statement_period(text)
    return (
        handler.get_statement_date(text),
        period_start,
        period_end,
        handler.get_opening_balance(text),
        handler.get_closing_balance(text),
    )


def identity_is_strong(key: tuple[object, ...]) -> bool:
    return any(part is not None for part in key)


def format_ambiguous_candidates(
    paths: list[Path],
    path_period_source: dict[Path, PeriodSource],
) -> str:
    return ", ".join(
        f"{path.name} ({period_source_for_path(path, path_period_source)})"
        for path in sorted(paths, key=lambda item: item.as_posix())
    )


def delete_staging_duplicates_for_month(
    download_dir: Path,
    month: str,
    path_month: dict[Path, str],
    *,
    keep: Path | None = None,
    preserve: frozenset[Path] | None = None,
    path_hash: dict[Path, str] | None = None,
    path_period_source: dict[Path, PeriodSource] | None = None,
) -> int:
    removed = 0
    keep_resolved = keep.resolve() if keep is not None else None
    preserve_resolved = (
        {path.resolve() for path in preserve} if preserve is not None else set()
    )
    keep_digest = (
        path_hash.get(keep) if keep is not None and path_hash is not None else None
    )
    if keep_digest is None and keep is not None:
        keep_digest = file_hash(keep)
    keep_rank = (
        period_source_rank(period_source_for_path(keep, path_period_source))
        if keep is not None and path_period_source is not None
        else None
    )
    for path in iter_pdfs(download_dir):
        if not is_staging_pdf(download_dir, path):
            continue
        if path_month.get(path) != month:
            continue
        if keep_resolved is not None and path.resolve() == keep_resolved:
            continue
        if path.resolve() in preserve_resolved:
            continue
        if keep_rank is not None and path_period_source is not None:
            path_rank = period_source_rank(
                period_source_for_path(path, path_period_source)
            )
            path_digest = path_hash.get(path) if path_hash is not None else None
            if path_digest is None:
                path_digest = file_hash(path)
            if path_digest != keep_digest and path_rank <= keep_rank:
                continue
        _ = path.unlink()
        logger.debug("removed (duplicate month): %s", path)
        removed += 1
    return removed


def select_keeper(
    unique: list[Path],
    *,
    account: ResolvedAccount,
    sanitized_by_path: dict[Path, str],
    path_period_source: dict[Path, PeriodSource],
    path_hash: dict[Path, str],
    text_contains: list[str],
    manual_candidates: list[Path],
) -> tuple[Path | None, list[Path]]:
    if manual_candidates:
        return manual_candidates[-1], []
    if not text_contains:
        return (unique[-1] if unique else None), []

    matching = [
        path
        for path in unique
        if text_contains_present(sanitized_by_path[path], text_contains)
    ]
    if not matching:
        return None, []

    matching_sorted = sorted(
        matching,
        key=lambda path: (
            period_source_rank(path_period_source.get(path, "unknown")),
            path.as_posix(),
        ),
    )
    best_rank = period_source_rank(
        path_period_source.get(matching_sorted[0], "unknown")
    )
    best = [
        path
        for path in matching_sorted
        if period_source_rank(path_period_source.get(path, "unknown")) == best_rank
    ]
    if len(best) == 1:
        return best[0], []

    digests = {path_hash.get(path) or file_hash(path) for path in best}
    if len(digests) == 1:
        return best[-1], []

    identity_by_path = {
        path: statement_identity_key(sanitized_by_path[path], account) for path in best
    }
    unique_identities = set(identity_by_path.values())
    if len(unique_identities) > 1:
        return None, best
    identity_key = next(iter(unique_identities))
    if not identity_is_strong(identity_key):
        return None, best

    dated = [(path, email_date_from_staging_filename(path.name)) for path in best]
    with_dates = [(path, received) for path, received in dated if received is not None]
    if with_dates:
        latest_date = max(received for _, received in with_dates)
        latest_paths = sorted(
            (path for path, received in with_dates if received == latest_date),
            key=lambda path: path.as_posix(),
        )
        keeper = latest_paths[-1]
        ignored = [path for path in best if path != keeper]
        if ignored:
            logger.debug(
                "collapsed re-issued statement: kept %s, ignored %s",
                keeper.name,
                ", ".join(path.name for path in ignored),
            )
        return keeper, []

    return best[-1], []
