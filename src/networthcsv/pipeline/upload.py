"""Save manually uploaded statement files before post-upload pipeline stages."""

from __future__ import annotations

import re
from pathlib import Path

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.path import (
    account_fy_dir,
    fy_folder_name,
    statement_csv_path,
    statement_pdf_path,
)

_UPLOAD_PDF_PREFIX = "manual__"
_MANUAL_UPLOAD_PATTERN = re.compile(
    rf"^{re.escape(_UPLOAD_PDF_PREFIX)}(\d{{4}}-\d{{2}})\.pdf$",
    re.IGNORECASE,
)


class StatementFileExistsError(FileExistsError):
    """Raised when the canonical statement file already exists."""


def month_stem_from_manual_upload(filename: str) -> str | None:
    """Return YYYY-MM from a manual upload staging PDF name, if it matches."""
    match = _MANUAL_UPLOAD_PATTERN.match(Path(filename).name)
    if match is None:
        return None
    return match.group(1)


def manual_upload_pdf_path(staging_dir: Path, statement_date: str) -> Path:
    return staging_dir / f"{_UPLOAD_PDF_PREFIX}{statement_date}.pdf"


def save_uploaded_pdf(
    staging_dir: Path,
    download_path: Path,
    account: ResolvedAccount,
    statement_date: str,
    content: bytes,
) -> Path:
    """Write a PDF to staging for cleanup; reject if canonical PDF already exists."""
    canonical = statement_pdf_path(download_path, account, statement_date)
    if canonical.is_file():
        raise StatementFileExistsError(
            f"statement file already exists: {canonical.name}"
        )

    _ = staging_dir.mkdir(parents=True, exist_ok=True)
    target = manual_upload_pdf_path(staging_dir, statement_date)
    _ = target.write_bytes(content)
    return target


def save_uploaded_csv(
    download_path: Path,
    account: ResolvedAccount,
    statement_date: str,
    content: bytes,
) -> Path:
    """Write a per-month CSV directly into the account FY folder."""
    target = statement_csv_path(download_path, account, statement_date)
    if target.is_file():
        raise StatementFileExistsError(f"statement file already exists: {target.name}")

    _ = account_fy_dir(download_path, account, fy_folder_name(statement_date)).mkdir(
        parents=True,
        exist_ok=True,
    )
    _ = target.write_bytes(content)
    return target
