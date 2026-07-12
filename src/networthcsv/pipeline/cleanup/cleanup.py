"""Prepare statement PDFs: decrypt, validate, extract once, write paired FY folder outputs."""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from networthcsv.utils.alerts.models import Alert, AlertKind
from networthcsv.utils.alerts.service import AlertService
from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.results import CleanupAccountResult
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_pdfs,
    iter_statement_pairs,
    pdf_path_for_txt,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
)
from networthcsv.utils.pdf import extract_pdf_text_plumber
from networthcsv.pipeline.cleanup.statement_date import (
    PeriodSource,
    resolve_statement_period_with_source,
)
from networthcsv.pipeline.upload import (
    manual_upload_pdf_path,
    period_from_manual_upload,
)
from networthcsv.utils.banks.helpers.text import (
    check_text_contains,
    statement_text_eligible,
    text_contains_present,
    text_not_contains_violated,
)
from networthcsv.settings import (
    ResolvedAccount,
    Settings,
    account_download_path,
    account_label,
)
from networthcsv.utils.statement_period import email_date_from_staging_filename

logger = logging.getLogger(__name__)

_PERIOD_SOURCE_RANK: dict[PeriodSource, int] = {
    "manual": -1,
    "yearly": 0,
    "content_date": 1,
    "filename_fallback": 2,
    "unknown": 3,
}


def _period_source_rank(source: PeriodSource) -> int:
    return _PERIOD_SOURCE_RANK[source]


def _period_source_for_path(
    path: Path,
    lookup: dict[Path, PeriodSource],
) -> PeriodSource:
    source = lookup.get(path)
    if source is not None:
        return source
    if period_from_manual_upload(path.name):
        return "manual"
    return "unknown"


@dataclass(frozen=True)
class MonthGroups:
    groups: dict[str, list[Path]]
    raw_by_path: dict[Path, str]
    path_month: dict[Path, str]
    path_hash: dict[Path, str]
    path_period_source: dict[Path, PeriodSource]


def _is_staging_pdf(download_dir: Path, path: Path) -> bool:
    try:
        _ = path.relative_to(download_dir)
    except ValueError:
        return False
    if path.parent == download_dir:
        return True
    return False


def _delete_staging_duplicates_for_month(
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
        keep_digest = _file_hash(keep)
    keep_rank = (
        _period_source_rank(_period_source_for_path(keep, path_period_source))
        if keep is not None and path_period_source is not None
        else None
    )
    for path in iter_pdfs(download_dir):
        if not _is_staging_pdf(download_dir, path):
            continue
        if path_month.get(path) != month:
            continue
        if keep_resolved is not None and path.resolve() == keep_resolved:
            continue
        if path.resolve() in preserve_resolved:
            continue
        if keep_rank is not None and path_period_source is not None:
            path_rank = _period_source_rank(
                _period_source_for_path(path, path_period_source)
            )
            path_digest = path_hash.get(path) if path_hash is not None else None
            if path_digest is None:
                path_digest = _file_hash(path)
            if path_digest != keep_digest and path_rank <= keep_rank:
                continue
        _ = path.unlink()
        logger.debug("removed (duplicate month): %s", path)
        removed += 1
    return removed


def prune_non_pdfs(download_dir: Path) -> int:
    removed = 0
    for path in sorted(download_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            continue
        _ = path.unlink()
        logger.debug("removed (non-pdf): %s", path)
        removed += 1
    return removed


def decrypt_pdfs_in_place(download_dir: Path, passwords: list[str]) -> int:
    decrypted = 0
    decrypt_candidates = list(dict.fromkeys(["", *passwords]))
    for path in iter_pdfs(download_dir):
        reader = PdfReader(str(path))
        if not reader.is_encrypted:
            logger.debug("skip (not encrypted): %s", path)
            continue
        for password in decrypt_candidates:
            if reader.decrypt(password) != 0:
                break
        else:
            raise StageError(
                f"none of {len(decrypt_candidates)} password(s) worked for {path}"
            )
        writer = PdfWriter()
        for page in reader.pages:
            _ = writer.add_page(page)
        with path.open("wb") as fh:
            _ = writer.write(fh)
        logger.debug("decrypted: %s", path)
        decrypted += 1
    return decrypted


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dedupe_paths_by_hash(
    paths: list[Path],
    *,
    path_hash: dict[Path, str] | None = None,
) -> list[Path]:
    seen: dict[str, Path] = {}
    for path in sorted(paths):
        digest = path_hash.get(path) if path_hash is not None else None
        if digest is None:
            digest = _file_hash(path)
        if digest not in seen:
            seen[digest] = path
    return list(seen.values())


def collect_month_groups(
    staging_dir: Path,
    account: ResolvedAccount,
    *,
    paths: list[Path] | None = None,
) -> MonthGroups:
    by_month: dict[str, list[Path]] = {}
    raw_by_path: dict[Path, str] = {}
    path_month: dict[Path, str] = {}
    path_hash: dict[Path, str] = {}
    path_period_source: dict[Path, PeriodSource] = {}
    seen: set[str] = set()
    hash_to_raw: dict[str, str] = {}
    pdf_paths = paths if paths is not None else list(iter_pdfs(staging_dir))
    for path in sorted(pdf_paths, key=lambda item: item.as_posix()):
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        digest = _file_hash(path)
        path_hash[path] = digest
        raw = hash_to_raw.get(digest)
        if raw is None:
            raw = extract_pdf_text_plumber(path, account.passwords)
            hash_to_raw[digest] = raw
        raw_by_path[path] = raw
        manual_month = period_from_manual_upload(path.name)
        if manual_month is not None:
            month = manual_month
            source: PeriodSource = "manual"
        else:
            month, source = resolve_statement_period_with_source(
                raw, path.name, account=account
            )
        path_month[path] = month
        path_period_source[path] = source
        by_month.setdefault(month, []).append(path)
    return MonthGroups(
        groups=by_month,
        raw_by_path=raw_by_path,
        path_month=path_month,
        path_hash=path_hash,
        path_period_source=path_period_source,
    )


def _write_txt_atomically(txt_path: Path, content: str) -> None:
    _ = txt_path.parent.mkdir(parents=True, exist_ok=True)
    temp = txt_path.with_suffix(f"{txt_path.suffix}.tmp")
    _ = temp.write_text(content, encoding="utf-8")
    _ = temp.replace(txt_path)


def _sanitized_text(raw: str, account: ResolvedAccount) -> str:
    from networthcsv.utils.banks import get_handler

    handler = get_handler(account.bank, account.variant)
    return handler.clean_text(raw)


def _write_statement_pair(
    staging_dir: Path,
    download_path: Path,
    month: str,
    keeper: Path,
    raw: str,
    account: ResolvedAccount,
) -> None:
    pdf_out = statement_pdf_path(download_path, account, month)
    txt_out = txt_path_for_pdf(pdf_out)
    purged = _sanitized_text(raw, account)

    _ = pdf_out.parent.mkdir(parents=True, exist_ok=True)
    if keeper.resolve() != pdf_out.resolve():
        _ = shutil.copy2(keeper, pdf_out)
    _write_txt_atomically(txt_out, purged)

    if _is_staging_pdf(staging_dir, keeper) and keeper.resolve() != pdf_out.resolve():
        _ = keeper.unlink()
        logger.debug("removed (staging): %s", keeper)

    logger.debug("prepared: %s + %s", pdf_out, txt_out)


def _remove_ineligible_canonical_outputs(
    download_path: Path,
    account: ResolvedAccount,
) -> int:
    text_contains = account.statement.text_contains
    text_not_contains = account.statement.text_not_contains
    if not text_not_contains:
        return 0

    removed = 0
    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        if not pdf_path.is_file() or not txt_path.is_file():
            continue
        if not txt_is_current(pdf_path, txt_path):
            continue
        txt_content = txt_path.read_text(encoding="utf-8")
        if statement_text_eligible(
            txt_content,
            text_contains=text_contains,
            text_not_contains=text_not_contains,
            is_manual=False,
        ):
            continue
        _ = pdf_path.unlink()
        _ = txt_path.unlink()
        logger.debug(
            "removed (text_not_contains): canonical outputs %s + %s",
            pdf_path,
            txt_path,
        )
        removed += 1
    return removed


def _statement_identity_key(
    text: str,
    account: ResolvedAccount,
) -> tuple[object, ...]:
    from networthcsv.utils.banks import get_handler

    handler = get_handler(account.bank, account.variant)
    period_start, period_end = handler.get_statement_period(text)
    return (
        handler.get_statement_date(text),
        period_start,
        period_end,
        handler.get_opening_balance(text),
        handler.get_closing_balance(text),
    )


def _identity_is_strong(key: tuple[object, ...]) -> bool:
    return any(part is not None for part in key)


def _format_ambiguous_candidates(
    paths: list[Path],
    path_period_source: dict[Path, PeriodSource],
) -> str:
    return ", ".join(
        f"{path.name} ({_period_source_for_path(path, path_period_source)})"
        for path in sorted(paths, key=lambda item: item.as_posix())
    )


def _select_keeper(
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
            _period_source_rank(path_period_source.get(path, "unknown")),
            path.as_posix(),
        ),
    )
    best_rank = _period_source_rank(
        path_period_source.get(matching_sorted[0], "unknown")
    )
    best = [
        path
        for path in matching_sorted
        if _period_source_rank(path_period_source.get(path, "unknown")) == best_rank
    ]
    if len(best) == 1:
        return best[0], []

    digests = {path_hash.get(path) or _file_hash(path) for path in best}
    if len(digests) == 1:
        return best[-1], []

    identity_by_path = {
        path: _statement_identity_key(sanitized_by_path[path], account) for path in best
    }
    unique_identities = set(identity_by_path.values())
    if len(unique_identities) > 1:
        return None, best
    identity_key = next(iter(unique_identities))
    if not _identity_is_strong(identity_key):
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

    unique = _dedupe_paths_by_hash(existing, path_hash=path_hash)
    if raw_by_path is None:
        raw_by_path = {
            path: extract_pdf_text_plumber(path, account.passwords) for path in unique
        }
    sanitized_by_path = {
        path: _sanitized_text(raw_by_path[path], account) for path in unique
    }
    period_source_lookup = path_period_source or {}
    hash_lookup = path_hash or {}
    label = account_label(account)
    pdf_out = statement_pdf_path(download_path, account, month)
    canonical = pdf_out if pdf_out.is_file() else None
    text_contains = account.statement.text_contains
    text_not_contains = account.statement.text_not_contains

    manual_candidates = [
        path for path in unique if period_from_manual_upload(path.name)
    ]
    manual_paths = frozenset(manual_candidates)
    for path in unique:
        if path in manual_paths:
            continue
        if text_not_contains_violated(sanitized_by_path[path], text_not_contains):
            if path.is_file():
                _ = path.unlink()
                logger.debug("removed (text_not_contains): %s", path)

    eligible = [
        path
        for path in unique
        if path.is_file()
        and (
            path in manual_paths
            or not text_not_contains_violated(
                sanitized_by_path[path], text_not_contains
            )
        )
    ]
    if not eligible:
        return 0, 1

    keeper, ambiguous_paths = _select_keeper(
        eligible,
        account=account,
        sanitized_by_path=sanitized_by_path,
        path_period_source=period_source_lookup,
        path_hash=hash_lookup,
        text_contains=text_contains,
        manual_candidates=[path for path in manual_candidates if path in eligible],
    )

    if ambiguous_paths:
        conflict_summary = _format_ambiguous_candidates(
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
    keeper_rank = _period_source_rank(
        _period_source_for_path(keeper, period_source_lookup)
    )
    keeper_digest = hash_lookup.get(keeper) or _file_hash(keeper)
    keeper_identity = _statement_identity_key(sanitized_by_path[keeper], account)
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
        path_rank = _period_source_rank(
            _period_source_for_path(path, period_source_lookup)
        )
        path_digest = hash_lookup.get(path) or _file_hash(path)
        same_identity = (
            _identity_is_strong(keeper_identity)
            and _statement_identity_key(sanitized_by_path[path], account)
            == keeper_identity
        )
        if path_digest == keeper_digest or path_rank > keeper_rank or same_identity:
            if path.is_file():
                _ = path.unlink()
                logger.debug("removed (duplicate month): %s", path)

    dedupe_lookup = (
        path_month if path_month is not None else {path: month for path in existing}
    )
    _ = _delete_staging_duplicates_for_month(
        staging_dir,
        month,
        dedupe_lookup,
        keep=keeper,
        preserve=preserve,
        path_hash=hash_lookup,
        path_period_source=period_source_lookup,
    )
    _write_statement_pair(staging_dir, download_path, month, keeper, raw, account)
    return 1, 0


def sweep_orphans(settings: Settings, account: ResolvedAccount) -> int:
    removed = 0
    for account_fy_dir in discover_account_fy_dirs(settings.download_path, account):
        for pdf_path in iter_pdfs(account_fy_dir):
            txt_path = txt_path_for_pdf(pdf_path)
            if txt_path.is_file():
                continue
            _ = pdf_path.unlink()
            logger.debug("removed (orphan pdf): %s", pdf_path)
            removed += 1
        for txt_path in sorted(account_fy_dir.glob("*.txt")):
            if txt_path.name == "transactions.csv":
                continue
            pdf_path = pdf_path_for_txt(txt_path)
            if pdf_path.is_file():
                continue
            _ = txt_path.unlink()
            logger.debug("removed (orphan txt): %s", txt_path)
            removed += 1
    return removed


def run(
    staging_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    upload_statement_date: str | None = None,
) -> CleanupAccountResult:
    if not staging_dir.is_dir():
        ctx.reporter.cleanup_skipped(account.bank, staging_dir)
        return CleanupAccountResult(
            bank=account.bank,
            download_dir=staging_dir,
            non_pdf_removed=0,
            decrypted=0,
            prepared=0,
            rejected=0,
            orphans_removed=0,
            skipped=True,
        )

    download_path = ctx.settings.download_path
    ctx.reporter.cleanup_started(account.bank, staging_dir)

    alerts = ctx.alerts
    removed = prune_non_pdfs(staging_dir)
    decrypted = decrypt_pdfs_in_place(staging_dir, account.passwords)

    prepared = 0
    rejected = 0
    if upload_statement_date is not None:
        upload_path = manual_upload_pdf_path(staging_dir, upload_statement_date)
        staging_paths = [upload_path] if upload_path.is_file() else []
    else:
        staging_paths = None
    collected = collect_month_groups(
        staging_dir,
        account,
        paths=staging_paths,
    )
    _ = _remove_ineligible_canonical_outputs(download_path, account)

    for month, candidates in sorted(collected.groups.items()):
        if month == "unknown-month":
            logger.debug(
                "skip unknown-month: leaving %d file(s) in %s",
                len(candidates),
                staging_dir,
            )
            continue

        pdf_out = statement_pdf_path(download_path, account, month)
        txt_out = txt_path_for_pdf(pdf_out)
        canonical = pdf_out if pdf_out.is_file() else None
        extra = [
            path
            for path in candidates
            if path.is_file()
            and (canonical is None or path.resolve() != canonical.resolve())
        ]
        if not extra:
            if (
                pdf_out.is_file()
                and txt_out.is_file()
                and txt_is_current(pdf_out, txt_out)
            ):
                txt_content = txt_out.read_text(encoding="utf-8")
                if statement_text_eligible(
                    txt_content,
                    text_contains=account.statement.text_contains,
                    text_not_contains=account.statement.text_not_contains,
                    is_manual=False,
                ):
                    continue
                _ = pdf_out.unlink()
                _ = txt_out.unlink()
                logger.debug(
                    "removed (text_not_contains): canonical outputs for %s",
                    month,
                )

        month_prepared, month_rejected = prepare_month(
            staging_dir,
            download_path,
            month,
            candidates,
            account,
            raw_by_path=collected.raw_by_path,
            path_month=collected.path_month,
            path_hash=collected.path_hash,
            path_period_source=collected.path_period_source,
            alerts=alerts,
        )
        prepared += month_prepared
        rejected += month_rejected

    orphans = sweep_orphans(ctx.settings, account)

    result = CleanupAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        non_pdf_removed=removed,
        decrypted=decrypted,
        prepared=prepared,
        rejected=rejected,
        orphans_removed=orphans,
    )
    ctx.reporter.cleanup_done(result)
    return result


def run_account(
    ctx: RunContext,
    account: ResolvedAccount,
    *,
    upload_statement_date: str | None = None,
) -> CleanupAccountResult:
    return run(
        account_download_path(ctx.settings, account),
        account,
        ctx,
        upload_statement_date=upload_statement_date,
    )


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(lambda: run_stage_main(run_account=run_account))


if __name__ == "__main__":
    main()
