"""Duplicate PDF/CSV resolution and keeper selection."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

from networthcsv.pipeline.cleanup.grouping import file_hash
from networthcsv.pipeline.cleanup.period_source import (
    period_source_for_path,
    period_source_rank,
)
from networthcsv.pipeline.cleanup.staging import is_staging_csv, is_staging_pdf
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.text import text_contains_present
from networthcsv.utils.banks.period import PeriodSource
from networthcsv.utils.path import iter_csvs, iter_pdfs
from networthcsv.utils.statement_period import email_date_from_staging_filename

logger = logging.getLogger(__name__)


def _statement_fields(
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


def statement_identity_key(
    text: str,
    account: ResolvedAccount,
) -> tuple[object, ...]:
    return _statement_fields(text, account)


def identity_is_strong(key: tuple[object, ...]) -> bool:
    return any(part is not None for part in key)


def statement_collapse_key(
    text: str,
    account: ResolvedAccount,
) -> tuple[object, ...]:
    handler = get_handler(account.bank, account.variant)
    reference = handler.get_statement_reference(text)
    statement_date = handler.get_statement_date(text)
    if reference is not None and statement_date is not None:
        return ("invoice", reference, statement_date)
    return ("identity", *statement_identity_key(text, account))


def collapse_is_strong(key: tuple[object, ...]) -> bool:
    if not key:
        return False
    if key[0] == "invoice":
        return True
    return identity_is_strong(key[1:])


def statement_richness_score(text: str, account: ResolvedAccount) -> int:
    return sum(1 for part in _statement_fields(text, account) if part is not None)


def _pick_keeper_by_richness_then_email(
    candidates: list[Path],
    *,
    sanitized_by_path: dict[Path, str],
    account: ResolvedAccount,
) -> Path | None:
    richness_by_path = {
        path: statement_richness_score(sanitized_by_path[path], account)
        for path in candidates
    }
    max_richness = max(richness_by_path.values())
    richest = [path for path in candidates if richness_by_path[path] == max_richness]
    if len(richest) == 1:
        return richest[0]

    dated = [(path, email_date_from_staging_filename(path.name)) for path in richest]
    with_dates = [(path, received) for path, received in dated if received is not None]
    if not with_dates:
        return None
    latest_date = max(received for _, received in with_dates)
    latest_paths = [path for path, received in with_dates if received == latest_date]
    if len(latest_paths) != 1:
        return None
    return latest_paths[0]


def format_ambiguous_candidates(
    paths: list[Path],
    path_period_source: dict[Path, PeriodSource],
) -> str:
    return ", ".join(
        f"{path.name} ({period_source_for_path(path, path_period_source)})"
        for path in sorted(paths, key=lambda item: item.as_posix())
    )


def _delete_staging_duplicates_for_month(
    download_dir: Path,
    month: str,
    path_month: dict[Path, str],
    *,
    iter_paths: Callable[[Path], Iterator[Path]],
    is_staging_file: Callable[[Path, Path], bool],
    keep: Path | None = None,
    preserve: frozenset[Path] | None = None,
    path_hash: dict[Path, str] | None = None,
    path_period_source: dict[Path, PeriodSource] | None = None,
    removed_log_label: str = "duplicate month",
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
    for path in iter_paths(download_dir):
        if not is_staging_file(download_dir, path):
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
        logger.debug("removed (%s): %s", removed_log_label, path)
        removed += 1
    return removed


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
    return _delete_staging_duplicates_for_month(
        download_dir,
        month,
        path_month,
        iter_paths=iter_pdfs,
        is_staging_file=is_staging_pdf,
        keep=keep,
        preserve=preserve,
        path_hash=path_hash,
        path_period_source=path_period_source,
        removed_log_label="duplicate month",
    )


def delete_staging_csv_duplicates_for_month(
    download_dir: Path,
    month: str,
    path_month: dict[Path, str],
    *,
    keep: Path | None = None,
    path_hash: dict[Path, str] | None = None,
    path_period_source: dict[Path, PeriodSource] | None = None,
) -> int:
    return _delete_staging_duplicates_for_month(
        download_dir,
        month,
        path_month,
        iter_paths=iter_csvs,
        is_staging_file=is_staging_csv,
        keep=keep,
        path_hash=path_hash,
        path_period_source=path_period_source,
        removed_log_label="duplicate csv month",
    )


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

    resolved, remainder = _rank_best_by_period_and_hash(
        unique,
        text_by_path=sanitized_by_path,
        path_period_source=path_period_source,
        path_hash=path_hash,
        text_contains=text_contains,
    )
    if remainder is None:
        return resolved, []

    best = remainder
    collapse_by_path = {
        path: statement_collapse_key(sanitized_by_path[path], account) for path in best
    }
    unique_collapse_keys = set(collapse_by_path.values())
    if len(unique_collapse_keys) > 1:
        handler = get_handler(account.bank, account.variant)
        layout_id = getattr(handler, "hdfc_layout_id", None) or getattr(
            handler, "swiggy_layout_id", None
        )
        for path in sorted(best, key=lambda item: item.as_posix()):
            text = sanitized_by_path[path]
            layout = layout_id(text) if callable(layout_id) else None
            logger.warning(
                "collapse-key mismatch: %s layout=%s ref=%s date=%s "
                "opening=%s closing=%s key=%s richness=%s",
                path.name,
                layout,
                handler.get_statement_reference(text),
                handler.get_statement_date(text),
                handler.get_opening_balance(text),
                handler.get_closing_balance(text),
                collapse_by_path[path],
                statement_richness_score(text, account),
            )
        return None, best
    collapse_key = next(iter(unique_collapse_keys))
    if not collapse_is_strong(collapse_key):
        return None, best

    keeper = _pick_keeper_by_richness_then_email(
        best,
        sanitized_by_path=sanitized_by_path,
        account=account,
    )
    if keeper is None:
        return None, best

    ignored = [path for path in best if path != keeper]
    if ignored:
        logger.debug(
            "collapsed re-issued statement: kept %s, ignored %s",
            keeper.name,
            ", ".join(path.name for path in ignored),
        )
    return keeper, []


def select_csv_keeper(
    unique: list[Path],
    *,
    raw_by_path: dict[Path, str],
    path_period_source: dict[Path, PeriodSource],
    path_hash: dict[Path, str],
    text_contains: list[str],
) -> tuple[Path | None, list[Path]]:
    if not unique:
        return None, []
    if not text_contains:
        return unique[-1], []

    resolved, remainder = _rank_best_by_period_and_hash(
        unique,
        text_by_path=raw_by_path,
        path_period_source=path_period_source,
        path_hash=path_hash,
        text_contains=text_contains,
    )
    if remainder is None:
        return resolved, []

    best = remainder
    dated = [(path, email_date_from_staging_filename(path.name)) for path in best]
    with_dates = [(path, received) for path, received in dated if received is not None]
    if with_dates:
        latest_date = max(received for _, received in with_dates)
        latest_paths = sorted(
            (path for path, received in with_dates if received == latest_date),
            key=lambda path: path.as_posix(),
        )
        return latest_paths[-1], []

    preferred = sorted(
        best,
        key=lambda path: (not path.name.startswith("manual__"), path.as_posix()),
    )
    keeper = preferred[-1]
    ignored = [path for path in best if path != keeper]
    if ignored:
        logger.debug(
            "collapsed ambiguous CSV period: kept %s, ignored %s",
            keeper.name,
            ", ".join(path.name for path in ignored),
        )
    return keeper, []


def _rank_best_by_period_and_hash(
    unique: list[Path],
    *,
    text_by_path: dict[Path, str],
    path_period_source: dict[Path, PeriodSource],
    path_hash: dict[Path, str],
    text_contains: list[str],
) -> tuple[Path | None, list[Path] | None]:
    """Shared text_contains + period-rank + same-hash resolution.

    Returns ``(keeper, None)`` when resolved in this prefix,
    ``(None, None)`` when no text_contains match,
    or ``(None, best)`` when still tied for the caller to finish.
    """
    matching = [
        path
        for path in unique
        if text_contains_present(text_by_path[path], text_contains)
    ]
    if not matching:
        return None, None

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
        return best[0], None

    digests = {path_hash.get(path) or file_hash(path) for path in best}
    if len(digests) == 1:
        return best[-1], None

    return None, best
