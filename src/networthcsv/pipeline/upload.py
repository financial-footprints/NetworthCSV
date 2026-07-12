"""Save manually uploaded statement files before post-upload pipeline stages."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.period import resolve_csv_period_key_with_source
from networthcsv.utils.path import (
    account_fy_dir,
    fy_folder_name,
    statement_csv_path,
    statement_pdf_path,
    unique_path,
)
from networthcsv.utils.zip_archive import (
    extract_csvs_from_zip,
    sanitize_zip_member_name,
)

from networthcsv.utils.statement_period import (
    is_calendar_year_period,
    is_fy_period,
    parse_month_period,
)

logger = logging.getLogger(__name__)

_UPLOAD_PDF_PREFIX = "manual__"
_MANUAL_UPLOAD_PATTERN = re.compile(
    rf"^{re.escape(_UPLOAD_PDF_PREFIX)}(\d{{4}}-\d{{2}})\.(?:pdf|csv)$",
    re.IGNORECASE,
)
_MANUAL_ANNUAL_UPLOAD_PATTERN = re.compile(
    rf"^{re.escape(_UPLOAD_PDF_PREFIX)}((?:FY\d{{2}}-\d{{4}})|(?:\d{{4}}))\.(?:pdf|csv)$",
    re.IGNORECASE,
)


class StatementFileExistsError(FileExistsError):
    """Raised when the canonical statement file already exists."""


def period_from_manual_upload(filename: str) -> str | None:
    """Return YYYY-MM or FY year key from a manual upload staging file name."""
    name = Path(filename).name
    annual_match = _MANUAL_ANNUAL_UPLOAD_PATTERN.match(name)
    if annual_match is not None:
        return annual_match.group(1)
    match = _MANUAL_UPLOAD_PATTERN.match(name)
    if match is None:
        return None
    return match.group(1)


def is_valid_statement_period(period: str) -> bool:
    return (
        parse_month_period(period) is not None
        or is_fy_period(period)
        or is_calendar_year_period(period)
    )


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


def save_uploaded_zip(
    staging_dir: Path,
    account: ResolvedAccount,
    content: bytes,
) -> list[Path]:
    """Extract CSVs from a ZIP into staging for cleanup."""
    extracted = extract_csvs_from_zip(content, account.passwords)
    _ = staging_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in extracted:
        csv_text = item.content.decode("utf-8", errors="replace")
        period, _ = resolve_csv_period_key_with_source(
            csv_text,
            item.inner_name,
            account=account,
        )
        if period != "unknown-month" and is_valid_statement_period(period):
            staging_name = f"{_UPLOAD_PDF_PREFIX}{period}.csv"
        else:
            safe_name = sanitize_zip_member_name(item.inner_name)
            staging_name = f"{_UPLOAD_PDF_PREFIX}{safe_name}"
            logger.warning(
                "zip csv period unknown for %s; staging as %s",
                item.inner_name,
                staging_name,
            )
        target = unique_path(staging_dir, staging_name)
        _ = target.write_bytes(item.content)
        written.append(target)
    return written
