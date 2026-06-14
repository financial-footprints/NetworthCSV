"""Path and FY folder helpers."""

from __future__ import annotations

import logging
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


def discover_fy_folders(download_dir: Path, limit: Path | None = None) -> list[Path]:
    if limit is not None:
        if not limit.is_dir():
            raise SystemExit(f"error: FY folder not found: {limit}")
        return [limit]
    folders = sorted(p for p in download_dir.glob("FY*") if p.is_dir())
    if not folders:
        logger.warning("no FY folders found under %s", download_dir)
    return folders


def txt_path_for_pdf(download_dir: Path, fy_dir: Path, pdf_path: Path) -> Path:
    return download_dir / "txt" / fy_dir.name / f"{pdf_path.stem}.txt"


def txt_is_current(pdf_path: Path, txt_path: Path) -> bool:
    if not txt_path.is_file():
        return False
    return txt_path.stat().st_mtime >= pdf_path.stat().st_mtime
