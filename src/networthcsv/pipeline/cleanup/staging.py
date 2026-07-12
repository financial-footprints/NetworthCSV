"""Staging directory file operations."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from networthcsv.errors import StageError
from networthcsv.pipeline.cleanup.exclusion import statement_should_exclude
from networthcsv.pipeline.cleanup.models import MonthGroups
from networthcsv.pipeline.upload import period_from_manual_upload
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.path import is_csv_path, is_pdf_path, iter_pdfs
from networthcsv.utils.zip_archive import password_candidates

logger = logging.getLogger(__name__)

_SUPPORTED_STAGING_SUFFIXES = frozenset({".pdf", ".csv"})


def _is_staging_file(
    download_dir: Path,
    path: Path,
    *,
    is_type,
) -> bool:
    try:
        _ = path.relative_to(download_dir)
    except ValueError:
        return False
    return path.parent == download_dir and is_type(path)


def is_staging_pdf(download_dir: Path, path: Path) -> bool:
    return _is_staging_file(download_dir, path, is_type=is_pdf_path)


def is_staging_csv(download_dir: Path, path: Path) -> bool:
    return _is_staging_file(download_dir, path, is_type=is_csv_path)


def prune_unsupported_staging_files(download_dir: Path) -> int:
    """Remove staging files that are neither PDF nor CSV."""
    removed = 0
    for path in sorted(download_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() in _SUPPORTED_STAGING_SUFFIXES:
            continue
        _ = path.unlink()
        logger.debug("removed (unsupported staging): %s", path)
        removed += 1
    return removed


def decrypt_pdfs_in_place(download_dir: Path, passwords: list[str]) -> int:
    decrypted = 0
    decrypt_candidates = password_candidates(passwords)
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


def prune_excluded_staging(
    staging_dir: Path,
    account: ResolvedAccount,
    collected: MonthGroups,
    *,
    csv_collected: MonthGroups | None = None,
) -> int:
    """Delete non-manual staging PDFs/CSVs that match exclusion markers."""
    handler = get_handler(account.bank, account.variant)
    removed = 0
    for path, raw in list(collected.raw_by_path.items()):
        if not path.is_file():
            continue
        if not is_staging_pdf(staging_dir, path):
            continue
        if period_from_manual_upload(path.name):
            continue
        sanitized = handler.clean_text(raw)
        if not statement_should_exclude(
            raw, sanitized, account=account, is_manual=False
        ):
            continue
        _ = path.unlink()
        logger.debug("removed (excluded statement): %s", path)
        removed += 1

    if csv_collected is not None:
        for path, raw in list(csv_collected.raw_by_path.items()):
            if not path.is_file():
                continue
            if not is_staging_csv(staging_dir, path):
                continue
            if period_from_manual_upload(path.name):
                continue
            if not statement_should_exclude(raw, raw, account=account, is_manual=False):
                continue
            _ = path.unlink()
            logger.debug("removed (excluded statement): %s", path)
            removed += 1
    return removed
