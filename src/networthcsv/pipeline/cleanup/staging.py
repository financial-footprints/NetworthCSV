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
from networthcsv.utils.path import iter_pdfs

logger = logging.getLogger(__name__)


def is_staging_pdf(download_dir: Path, path: Path) -> bool:
    try:
        _ = path.relative_to(download_dir)
    except ValueError:
        return False
    if path.parent == download_dir:
        return True
    return False


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


def prune_excluded_staging(
    staging_dir: Path,
    account: ResolvedAccount,
    collected: MonthGroups,
) -> int:
    """Delete non-manual staging PDFs that match handler/config exclusion markers."""
    removed = 0
    for path, raw in list(collected.raw_by_path.items()):
        if not path.is_file():
            continue
        if not is_staging_pdf(staging_dir, path):
            continue
        if period_from_manual_upload(path.name):
            continue
        sanitized = get_handler(account.bank, account.variant).clean_text(raw)
        if not statement_should_exclude(
            raw, sanitized, account=account, is_manual=False
        ):
            continue
        _ = path.unlink()
        logger.debug("removed (excluded statement): %s", path)
        removed += 1
    return removed
