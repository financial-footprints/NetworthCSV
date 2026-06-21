"""Path and FY folder helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


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


def fy_folder_name(month_stem: str) -> str:
    if month_stem == "unknown-month":
        return "unknown-month"
    year_str, month_str = month_stem.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    if month >= 4:
        fy_start, fy_end = year, year + 1
    else:
        fy_start, fy_end = year - 1, year
    return f"FY{fy_start % 100:02d}-{fy_end}"


def fy_dir(download_dir: Path, fy_name: str) -> Path:
    return download_dir / fy_name


def statement_pdf_path(download_dir: Path, month_stem: str) -> Path:
    return fy_dir(download_dir, fy_folder_name(month_stem)) / f"{month_stem}.pdf"


def discover_fy_folders(download_dir: Path, limit: Path | None = None) -> list[Path]:
    if limit is not None:
        if not limit.is_dir():
            raise SystemExit(f"error: FY folder not found: {limit}")
        return [limit]
    folders = sorted(p for p in download_dir.glob("FY*") if p.is_dir())
    if not folders:
        logger.warning("no FY folders found under %s", download_dir)
    return folders


def txt_path_for_pdf(_download_dir: Path, pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".txt")


def pdf_path_for_txt(_download_dir: Path, txt_path: Path) -> Path:
    return txt_path.with_suffix(".pdf")


def txt_is_current(pdf_path: Path, txt_path: Path) -> bool:
    if not txt_path.is_file():
        return False
    return txt_path.stat().st_mtime >= pdf_path.stat().st_mtime


def iter_statement_pairs(
    download_dir: Path, fy_limit: Path | None = None
) -> Iterator[tuple[Path, Path]]:
    """Yield (pdf_path, txt_path) for each statement PDF in FY* folders."""
    for folder in discover_fy_folders(download_dir, fy_limit):
        for pdf_path in sorted(folder.glob("*.pdf")):
            yield pdf_path, txt_path_for_pdf(download_dir, pdf_path)


def pdfs_in_fy(download_dir: Path, fy_dir_path: Path) -> list[Path]:
    if fy_dir_path.parent != download_dir:
        return []
    return sorted(fy_dir_path.glob("*.pdf"))


def resolve_fy_limit(download_dir: Path, fy_name: str | None) -> Path | None:
    if fy_name is None:
        return None
    limit = Path(fy_name).expanduser()
    if not limit.is_absolute():
        limit = (download_dir / limit.name).resolve()
    return limit
