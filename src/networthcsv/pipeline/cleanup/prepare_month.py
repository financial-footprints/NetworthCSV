"""Per-month statement preparation orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from networthcsv.pipeline.cleanup.canonical import (
    sanitized_text,
    write_statement_pair,
)
from networthcsv.pipeline.cleanup.exclusion import statement_should_exclude
from networthcsv.pipeline.cleanup.grouping import dedupe_paths_by_hash, file_hash
from networthcsv.pipeline.cleanup.keeper import (
    delete_staging_duplicates_for_month,
    format_ambiguous_candidates,
    identity_is_strong,
    select_keeper,
    statement_identity_key,
)
from networthcsv.pipeline.cleanup.period_source import (
    period_source_for_path,
    period_source_rank,
)
from networthcsv.pipeline.upload import period_from_manual_upload
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account import account_label
from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks.helpers.text import (
    check_text_contains,
    text_contains_present,
)
from networthcsv.utils.banks.period import PeriodSource
from networthcsv.utils.path import statement_pdf_path
import networthcsv.utils.pdf as pdf

logger = logging.getLogger(__name__)


def prepare_month(
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
    """Resolve one statement month. Returns (prepared, rejected) counts."""
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return 0, 0

    unique = dedupe_paths_by_hash(existing, path_hash=path_hash)
    if raw_by_path is None:
        raw_by_path = {
            path: pdf.extract_pdf_text_plumber(path, account.passwords)
            for path in unique
        }
    sanitized_by_path = {
        path: sanitized_text(raw_by_path[path], account) for path in unique
    }
    period_source_lookup = path_period_source or {}
    hash_lookup = path_hash or {}
    label = account_label(account)
    pdf_out = statement_pdf_path(download_path, account, month)
    canonical = pdf_out if pdf_out.is_file() else None
    text_contains = account.statement.text_contains

    manual_candidates = [
        path for path in unique if period_from_manual_upload(path.name)
    ]
    manual_paths = frozenset(manual_candidates)
    for path in unique:
        if path in manual_paths:
            continue
        if statement_should_exclude(
            raw_by_path[path],
            sanitized_by_path[path],
            account=account,
            is_manual=False,
        ):
            if path.is_file():
                _ = path.unlink()
                logger.debug("removed (excluded statement): %s", path)

    eligible = [
        path
        for path in unique
        if path.is_file()
        and (
            path in manual_paths
            or not statement_should_exclude(
                raw_by_path[path],
                sanitized_by_path[path],
                account=account,
                is_manual=False,
            )
        )
    ]
    if not eligible:
        return 0, 1

    keeper, ambiguous_paths = select_keeper(
        eligible,
        account=account,
        sanitized_by_path=sanitized_by_path,
        path_period_source=period_source_lookup,
        path_hash=hash_lookup,
        text_contains=text_contains,
        manual_candidates=[path for path in manual_candidates if path in eligible],
    )

    if ambiguous_paths:
        conflict_summary = format_ambiguous_candidates(
            ambiguous_paths,
            period_source_lookup,
        )
        logger.warning(
            "ambiguous statement period for %s: %s for month %s; "
            "leaving files in staging",
            label,
            conflict_summary,
            month,
        )
        if alerts is not None:
            alerts.emit(
                Alert(
                    kind=AlertKind.AMBIGUOUS_STATEMENT_PERIOD,
                    message=(
                        f"multiple matching PDFs with same period confidence "
                        f"for {month}: {conflict_summary}; manual review required"
                    ),
                    account=label,
                    source_file=month,
                    text_contains=list(text_contains),
                )
            )
        return 0, 1

    if keeper is None:
        for path in eligible:
            if canonical is not None and path.resolve() == canonical.resolve():
                continue
            if text_contains:
                _ = check_text_contains(
                    sanitized_by_path[path],
                    text_contains=text_contains,
                    source_file=path.name,
                    account_label=label,
                    alerts=alerts,
                )
        return 0, 1

    raw = raw_by_path[keeper]
    keeper_is_manual = keeper in manual_paths
    keeper_rank = period_source_rank(
        period_source_for_path(keeper, period_source_lookup)
    )
    keeper_digest = hash_lookup.get(keeper) or file_hash(keeper)
    keeper_identity = statement_identity_key(sanitized_by_path[keeper], account)
    preserve: frozenset[Path] = frozenset()
    if text_contains and not keeper_is_manual:
        preserve = frozenset(
            path
            for path in eligible
            if path != keeper
            and not text_contains_present(sanitized_by_path[path], text_contains)
        )
    for path in eligible:
        if path == keeper:
            continue
        if keeper_is_manual or not text_contains_present(
            sanitized_by_path[path], text_contains
        ):
            if text_contains and not keeper_is_manual:
                _ = check_text_contains(
                    sanitized_by_path[path],
                    text_contains=text_contains,
                    source_file=path.name,
                    account_label=label,
                    alerts=alerts,
                )
            continue
        path_rank = period_source_rank(
            period_source_for_path(path, period_source_lookup)
        )
        path_digest = hash_lookup.get(path) or file_hash(path)
        same_identity = (
            identity_is_strong(keeper_identity)
            and statement_identity_key(sanitized_by_path[path], account)
            == keeper_identity
        )
        if path_digest == keeper_digest or path_rank > keeper_rank or same_identity:
            if path.is_file():
                _ = path.unlink()
                logger.debug("removed (duplicate month): %s", path)

    dedupe_lookup = (
        path_month if path_month is not None else {path: month for path in existing}
    )
    _ = delete_staging_duplicates_for_month(
        staging_dir,
        month,
        dedupe_lookup,
        keep=keeper,
        preserve=preserve,
        path_hash=hash_lookup,
        path_period_source=period_source_lookup,
    )
    write_statement_pair(staging_dir, download_path, month, keeper, raw, account)
    return 1, 0
