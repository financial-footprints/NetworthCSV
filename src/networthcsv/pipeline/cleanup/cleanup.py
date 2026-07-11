"""Prepare statement PDFs: decrypt, validate, extract once, write paired FY folder outputs."""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from networthcsv.utils.alerts.service import AlertService
from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.results import CleanupAccountResult
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_pdfs,
    pdf_path_for_txt,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
)
from networthcsv.utils.pdf import extract_pdf_text_plumber
from networthcsv.pipeline.cleanup.statement_date import resolve_month_stem
from networthcsv.pipeline.upload import (
    month_stem_from_manual_upload,
    manual_upload_pdf_path,
)
from networthcsv.utils.banks.helpers.text import (
    check_text_contains,
    text_contains_present,
)
from networthcsv.settings import (
    ResolvedAccount,
    Settings,
    account_download_path,
    account_label,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonthGroups:
    groups: dict[str, list[Path]]
    raw_by_path: dict[Path, str]
    path_month: dict[Path, str]
    path_hash: dict[Path, str]


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
) -> int:
    removed = 0
    keep_resolved = keep.resolve() if keep is not None else None
    preserve_resolved = (
        {path.resolve() for path in preserve} if preserve is not None else set()
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
    for path in iter_pdfs(download_dir):
        reader = PdfReader(str(path))
        if not reader.is_encrypted:
            logger.debug("skip (already decrypted): %s", path)
            continue
        if not passwords:
            raise StageError(f"encrypted PDF requires password: {path}")
        for password in passwords:
            if reader.decrypt(password) != 0:
                break
        else:
            raise StageError(f"none of {len(passwords)} password(s) worked for {path}")
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
        manual_month = month_stem_from_manual_upload(path.name)
        if manual_month is not None:
            month = manual_month
        else:
            month = resolve_month_stem(raw, path.name, account=account)
        path_month[path] = month
        by_month.setdefault(month, []).append(path)
    return MonthGroups(
        groups=by_month,
        raw_by_path=raw_by_path,
        path_month=path_month,
        path_hash=path_hash,
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
    label = account_label(account)
    pdf_out = statement_pdf_path(download_path, account, month)
    canonical = pdf_out if pdf_out.is_file() else None
    text_contains = account.statement.text_contains

    keeper = None
    manual_candidates = [
        path for path in unique if month_stem_from_manual_upload(path.name)
    ]
    if manual_candidates:
        keeper = manual_candidates[-1]
    elif text_contains:
        for path in unique:
            if text_contains_present(sanitized_by_path[path], text_contains):
                keeper = path
    elif unique:
        keeper = unique[-1]

    if keeper is None:
        for path in unique:
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
    keeper_is_manual = keeper in manual_candidates
    preserve: frozenset[Path] = frozenset()
    if text_contains and not keeper_is_manual:
        preserve = frozenset(
            path
            for path in unique
            if path != keeper
            and not text_contains_present(sanitized_by_path[path], text_contains)
        )
    for path in unique:
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
        elif path.is_file():
            _ = path.unlink()
            logger.debug("removed (duplicate month): %s", path)

    dedupe_lookup = (
        path_month if path_month is not None else {path: month for path in existing}
    )
    _ = _delete_staging_duplicates_for_month(
        staging_dir, month, dedupe_lookup, keep=keeper, preserve=preserve
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
                if not account.statement.text_contains or text_contains_present(
                    txt_content, account.statement.text_contains
                ):
                    continue

        month_prepared, month_rejected = prepare_month(
            staging_dir,
            download_path,
            month,
            candidates,
            account,
            raw_by_path=collected.raw_by_path,
            path_month=collected.path_month,
            path_hash=collected.path_hash,
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
