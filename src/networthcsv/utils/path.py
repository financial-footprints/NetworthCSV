"""Path and FY folder helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from networthcsv.errors import StageError
from networthcsv.utils.statement_period import (
    is_annual_period,
    is_calendar_year_period,
    is_fy_period,
    parse_month_period,
)

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount

logger = logging.getLogger(__name__)

_PDF_SUFFIX = ".pdf"
_CSV_SUFFIX = ".csv"

FISCAL_YEAR_BASENAME = "fiscal_year"


def is_pdf_path(path: Path) -> bool:
    return path.suffix.lower() == _PDF_SUFFIX


def is_csv_path(path: Path) -> bool:
    return path.suffix.lower() == _CSV_SUFFIX


def iter_pdfs(directory: Path, *, recursive: bool = False) -> Iterator[Path]:
    """Yield PDF paths regardless of .pdf/.PDF extension."""
    if not directory.is_dir():
        return
    walker = directory.rglob("*") if recursive else directory.iterdir()
    for path in sorted(walker, key=lambda item: item.as_posix()):
        if path.is_file() and is_pdf_path(path):
            yield path


def iter_csvs(directory: Path, *, recursive: bool = False) -> Iterator[Path]:
    """Yield CSV paths regardless of .csv/.CSV extension."""
    if not directory.is_dir():
        return
    walker = directory.rglob("*") if recursive else directory.iterdir()
    for path in sorted(walker, key=lambda item: item.as_posix()):
        if path.is_file() and is_csv_path(path):
            yield path


def unique_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while True:
        candidate = directory / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def statement_basename(statement_period: str) -> str:
    """Return the on-disk filename stem for a statement period key."""
    if is_annual_period(statement_period):
        return FISCAL_YEAR_BASENAME
    return statement_period


def fy_folder_name(statement_period: str) -> str:
    if statement_period == "unknown-month":
        return "unknown-month"
    if is_fy_period(statement_period) or is_calendar_year_period(statement_period):
        return statement_period
    year_str, month_str = statement_period.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    fy_start, fy_end = (year, year + 1) if month >= 4 else (year - 1, year)
    return f"FY{fy_start % 100:02d}-{fy_end}"


def account_fy_dir(download_path: Path, account: ResolvedAccount, fy_name: str) -> Path:
    return download_path / fy_name / account.account_type / account.account_number


def account_metadata_path(download_path: Path, account: ResolvedAccount) -> Path:
    return (
        download_path / account.account_type / account.account_number / "metadata.json"
    )


def account_download_path(download_path: Path, account: ResolvedAccount) -> Path:
    return download_path / account.account_type / account.account_number


def statement_pdf_path(
    download_path: Path, account: ResolvedAccount, statement_period: str
) -> Path:
    basename = statement_basename(statement_period)
    return (
        account_fy_dir(download_path, account, fy_folder_name(statement_period))
        / f"{basename}.pdf"
    )


def statement_csv_path(
    download_path: Path, account: ResolvedAccount, statement_period: str
) -> Path:
    basename = statement_basename(statement_period)
    return (
        account_fy_dir(download_path, account, fy_folder_name(statement_period))
        / f"{basename}.csv"
    )


def fy_folder_name_from_statement_path(path: Path) -> str | None:
    """Return the FY folder name for a canonical statement file path."""
    if path.stem == FISCAL_YEAR_BASENAME:
        fy_name = path.parent.parent.parent.name
        if is_fy_period(fy_name) or is_calendar_year_period(fy_name):
            return fy_name
    if is_annual_period(path.stem):
        return path.stem
    return None


def statement_period_from_path(path: Path) -> str | None:
    """Return the statement period key encoded by a canonical on-disk path."""
    if parse_month_period(path.stem) is not None:
        return path.stem
    fy_name = fy_folder_name_from_statement_path(path)
    if fy_name is not None:
        return fy_name
    return None


_MONTH_PERIOD_GLOB = "????-??"
_STATEMENT_CSV_SUFFIX = ".csv"
_TRANSACTIONS_CSV = "transactions.csv"


def discover_account_fy_dirs(
    download_path: Path,
    account: ResolvedAccount,
    limit: Path | None = None,
) -> list[Path]:
    if limit is not None:
        if not limit.is_dir():
            raise StageError(f"FY folder not found: {limit}")
        return [limit]
    dirs: list[Path] = []
    for fy in sorted(download_path.glob("FY*")):
        if not fy.is_dir():
            continue
        path = account_fy_dir(download_path, account, fy.name)
        if path.is_dir():
            dirs.append(path)
    for year_dir in sorted(download_path.glob("[0-9][0-9][0-9][0-9]")):
        if not year_dir.is_dir():
            continue
        path = account_fy_dir(download_path, account, year_dir.name)
        if path.is_dir():
            dirs.append(path)
    if not dirs:
        logger.warning(
            "no account FY folders found for %s under %s",
            account.account_number,
            download_path,
        )
    return dirs


def txt_path_for_pdf(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".txt")


def pdf_path_for_txt(txt_path: Path) -> Path:
    return txt_path.with_suffix(".pdf")


def txt_is_current(pdf_path: Path, txt_path: Path) -> bool:
    if not txt_path.is_file():
        return False
    return txt_path.stat().st_mtime >= pdf_path.stat().st_mtime


def iter_statement_pairs(
    download_path: Path,
    account: ResolvedAccount,
    fy_limit: Path | None = None,
) -> Iterator[tuple[Path, Path]]:
    """Yield (pdf_path, txt_path) for each statement PDF in account FY folders."""
    for folder in discover_account_fy_dirs(download_path, account, fy_limit):
        for pdf_path in iter_pdfs(folder):
            yield pdf_path, txt_path_for_pdf(pdf_path)


def iter_statement_csvs(
    download_path: Path,
    account: ResolvedAccount,
    fy_limit: Path | None = None,
) -> Iterator[Path]:
    """Yield per-period statement CSV paths (excludes transactions.csv)."""
    for folder in discover_account_fy_dirs(download_path, account, fy_limit):
        patterns = (
            f"{_MONTH_PERIOD_GLOB}{_STATEMENT_CSV_SUFFIX}",
            f"{FISCAL_YEAR_BASENAME}{_STATEMENT_CSV_SUFFIX}",
        )
        seen: set[Path] = set()
        for pattern in patterns:
            for path in sorted(folder.glob(pattern)):
                if (
                    path.is_file()
                    and path.name != _TRANSACTIONS_CSV
                    and path not in seen
                ):
                    seen.add(path)
                    yield path


def resolve_fy_limit(
    download_path: Path,
    account: ResolvedAccount,
    fy_name: str | None,
) -> Path | None:
    if fy_name is None:
        return None
    limit = Path(fy_name).expanduser()
    if not limit.is_absolute():
        limit = account_fy_dir(download_path, account, limit.name)
    return limit.resolve()
