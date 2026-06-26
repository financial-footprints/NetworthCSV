#!/usr/bin/env python3
"""Prepare statement PDFs: decrypt, validate, extract once, write paired FY folder outputs."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from src.utils.alerts.service import AlertService
from src.context import RunContext
from src.utils.paths import (
    iter_pdfs,
    pdf_path_for_txt,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
    unique_path,
)
from src.utils.pdf import extract_pdf_text_plumber, open_pdf_reader
from src.pipeline.cleanup.statement_text import (
    check_identifier,
    identifier_present,
    purge_information_markers,
    sanitize_statement_text,
    trim_by_markers,
)
from src.settings import ResolvedAccount, account_label

logger = logging.getLogger(__name__)

_LEGACY_PDF_ROOT = "PDF"
_LEGACY_TXT_ROOT = "TXT"
_UNKNOWN_DIR = "unknown"

_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")


def _month_stem_from_name(filename: str) -> str:
    match = _DATE_IN_NAME.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"


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
    *,
    keep: Path | None = None,
) -> int:
    removed = 0
    keep_resolved = keep.resolve() if keep is not None else None
    for path in iter_pdfs(download_dir):
        if not _is_staging_pdf(download_dir, path):
            continue
        if _month_stem_from_name(path.name) != month:
            continue
        if keep_resolved is not None and path.resolve() == keep_resolved:
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
        reader = open_pdf_reader(path, passwords)
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


def _dedupe_paths_by_hash(paths: list[Path]) -> list[Path]:
    seen: dict[str, Path] = {}
    for path in sorted(paths):
        digest = _file_hash(path)
        if digest not in seen:
            seen[digest] = path
    return list(seen.values())


def collect_month_groups(download_dir: Path) -> dict[str, list[Path]]:
    by_month: dict[str, list[Path]] = {}
    seen: set[str] = set()
    paths = list(iter_pdfs(download_dir))
    for fy_dir in download_dir.glob("FY*"):
        if fy_dir.is_dir():
            paths.extend(iter_pdfs(fy_dir))
    for path in sorted(paths, key=lambda item: item.as_posix()):
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        month = _month_stem_from_name(path.name)
        by_month.setdefault(month, []).append(path)
    return by_month


def _move_to_unknown(download_dir: Path, path: Path) -> Path:
    dest_dir = download_dir / _UNKNOWN_DIR
    _ = dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir, path.name)
    _ = shutil.move(path, dest)
    logger.debug("quarantined (wrong statement): %s -> %s", path, dest)
    return dest


def _write_txt_atomically(txt_path: Path, content: str) -> None:
    _ = txt_path.parent.mkdir(parents=True, exist_ok=True)
    temp = txt_path.with_suffix(f"{txt_path.suffix}.tmp")
    _ = temp.write_text(content, encoding="utf-8")
    _ = temp.replace(txt_path)


def _sanitized_text(raw: str, account: ResolvedAccount) -> str:
    trimmed = trim_by_markers(
        raw,
        start_marker=account.start_marker,
        end_marker=account.end_marker,
    )
    sanitized = sanitize_statement_text(trimmed)
    return purge_information_markers(
        sanitized,
        information_markers=account.information_markers,
    )


def _write_statement_pair(
    download_dir: Path,
    month: str,
    keeper: Path,
    raw: str,
    account: ResolvedAccount,
) -> None:
    pdf_out = statement_pdf_path(download_dir, month)
    txt_out = txt_path_for_pdf(download_dir, pdf_out)
    purged = _sanitized_text(raw, account)

    _ = pdf_out.parent.mkdir(parents=True, exist_ok=True)
    if keeper.resolve() != pdf_out.resolve():
        _ = shutil.copy2(keeper, pdf_out)
    _write_txt_atomically(txt_out, purged)

    if _is_staging_pdf(download_dir, keeper) and keeper.resolve() != pdf_out.resolve():
        _ = keeper.unlink()
        logger.debug("removed (staging): %s", keeper)

    logger.debug("prepared: %s + %s", pdf_out, txt_out)


def prepare_month(
    download_dir: Path,
    month: str,
    candidates: list[Path],
    account: ResolvedAccount,
    *,
    alerts: AlertService | None = None,
) -> tuple[int, int]:
    """Resolve one statement month. Returns (prepared, rejected) counts."""
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return 0, 0

    unique = _dedupe_paths_by_hash(existing)
    raw_by_path = {
        path: extract_pdf_text_plumber(path, account.passwords) for path in unique
    }
    sanitized_by_path = {
        path: _sanitized_text(raw, account) for path, raw in raw_by_path.items()
    }
    label = account_label(account)
    pdf_out = statement_pdf_path(download_dir, month)
    canonical = pdf_out if pdf_out.is_file() else None

    keeper = None
    for path in unique:
        if identifier_present(sanitized_by_path[path], account.identifier):
            keeper = path

    if keeper is None:
        for path in unique:
            if canonical is not None and path.resolve() == canonical.resolve():
                continue
            _ = check_identifier(
                sanitized_by_path[path],
                identifier=account.identifier,
                source_file=path.name,
                account_label=label,
                alerts=alerts,
            )
            if path.is_file():
                _ = _move_to_unknown(download_dir, path)
        _ = _delete_staging_duplicates_for_month(download_dir, month)
        return 0, 1

    raw = raw_by_path[keeper]
    for path in unique:
        if path == keeper:
            continue
        if not identifier_present(sanitized_by_path[path], account.identifier):
            _ = check_identifier(
                sanitized_by_path[path],
                identifier=account.identifier,
                source_file=path.name,
                account_label=label,
                alerts=alerts,
            )
            if path.is_file():
                _ = _move_to_unknown(download_dir, path)
        elif path.is_file():
            _ = path.unlink()
            logger.debug("removed (duplicate month): %s", path)

    _ = _delete_staging_duplicates_for_month(download_dir, month, keep=keeper)
    _write_statement_pair(download_dir, month, keeper, raw, account)
    return 1, 0


def sweep_orphans(download_dir: Path) -> int:
    removed = 0
    for fy_dir in sorted(download_dir.glob("FY*")):
        if not fy_dir.is_dir():
            continue
        for pdf_path in iter_pdfs(fy_dir):
            txt_path = txt_path_for_pdf(download_dir, pdf_path)
            if txt_path.is_file():
                continue
            _ = pdf_path.unlink()
            logger.debug("removed (orphan pdf): %s", pdf_path)
            removed += 1
        for txt_path in sorted(fy_dir.glob("*.txt")):
            if txt_path.name == "transactions.csv":
                continue
            pdf_path = pdf_path_for_txt(download_dir, txt_path)
            if pdf_path.is_file():
                continue
            _ = txt_path.unlink()
            logger.debug("removed (orphan txt): %s", txt_path)
            removed += 1
    return removed


def sweep_legacy_layout(download_dir: Path) -> int:
    removed = 0
    for name in (_LEGACY_PDF_ROOT, _LEGACY_TXT_ROOT):
        legacy = download_dir / name
        if legacy.is_dir():
            shutil.rmtree(legacy)
            logger.debug("removed (legacy layout): %s", legacy)
            removed += 1
    return removed


def run(
    download_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext | None = None,
) -> None:
    if not download_dir.is_dir():
        raise SystemExit(f"error: download directory not found: {download_dir}")

    print(f"cleanup: {account.bank} {download_dir}")
    force = ctx.settings.run.force_text_extract if ctx is not None else False
    if force:
        print("force: re-preparing all statement pairs")
    print()

    alerts = ctx.alerts if ctx is not None else None
    removed = prune_non_pdfs(download_dir)
    decrypted = decrypt_pdfs_in_place(download_dir, account.passwords)

    prepared = 0
    rejected = 0
    month_groups = collect_month_groups(download_dir)

    for month, candidates in sorted(month_groups.items()):
        pdf_out = statement_pdf_path(download_dir, month)
        txt_out = txt_path_for_pdf(download_dir, pdf_out)
        canonical = pdf_out if pdf_out.is_file() else None
        extra = [
            path
            for path in candidates
            if path.is_file()
            and (canonical is None or path.resolve() != canonical.resolve())
        ]
        if not extra and not force:
            if pdf_out.is_file() and txt_out.is_file() and txt_is_current(pdf_out, txt_out):
                txt_content = txt_out.read_text(encoding="utf-8")
                if identifier_present(txt_content, account.identifier):
                    continue

        month_prepared, month_rejected = prepare_month(
            download_dir,
            month,
            candidates,
            account,
            alerts=alerts,
        )
        prepared += month_prepared
        rejected += month_rejected

    orphans = sweep_orphans(download_dir)
    legacy = sweep_legacy_layout(download_dir)

    print()
    print(
        f"done: {removed} non-pdf removed, {decrypted} decrypted, {prepared} prepared, "
        + f"{rejected} rejected (identifier missing), {orphans} orphan(s) removed, "
        + f"{legacy} legacy folder(s) removed"
    )


def main() -> None:
    from src.cli import run_stage_main

    def run_account(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
        run(download_dir, account, ctx)

    run_stage_main(run_account=run_account)


if __name__ == "__main__":
    main()
