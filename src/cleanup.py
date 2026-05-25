#!/usr/bin/env python3
"""Clean downloaded statements: keep PDFs only, decrypt, dedupe, rename, organize by FY."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from src.config import load_settings, require_pdf_password
from src.extractor import unique_path

_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?")
_DUP_SUFFIX = re.compile(r" \(\d+\)$")


def prune_non_pdfs(download_dir: Path) -> int:
    removed = 0
    for path in sorted(download_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            continue
        path.unlink()
        print(f"removed (non-pdf): {path}")
        removed += 1
    return removed


def decrypt_pdfs_in_place(download_dir: Path, password: str) -> int:
    decrypted = 0
    for path in sorted(download_dir.glob("*.pdf")):
        reader = PdfReader(str(path))
        if not reader.is_encrypted:
            print(f"skip (already decrypted): {path}")
            continue
        if reader.decrypt(password) == 0:
            raise SystemExit(f"error: wrong pdf password for {path}")
        writer = PdfWriter()
        for page in reader.pages:
            _ = writer.add_page(page)
        with path.open("wb") as fh:
            _ = writer.write(fh)
        print(f"decrypted: {path}")
        decrypted += 1
    return decrypted


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _keep_priority(path: Path) -> tuple[bool, str]:
    has_dup_suffix = bool(_DUP_SUFFIX.search(path.stem))
    return (has_dup_suffix, path.as_posix())


def dedupe_pdfs(download_dir: Path) -> int:
    by_hash: dict[str, list[Path]] = {}
    for path in sorted(download_dir.glob("*.pdf")):
        digest = _file_hash(path)
        by_hash.setdefault(digest, []).append(path)

    deleted = 0
    for paths in by_hash.values():
        if len(paths) <= 1:
            continue
        keep = min(paths, key=_keep_priority)
        for path in paths:
            if path == keep:
                continue
            path.unlink()
            print(f"removed (duplicate of {keep.name}): {path}")
            deleted += 1
    return deleted


def _month_stem_from_name(filename: str) -> str:
    match = _DATE_IN_NAME.search(filename)
    if match:
        return match.group(1)
    return "unknown-month"


def _fy_folder_name(month_stem: str) -> str:
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


def organize_by_financial_year(download_dir: Path) -> int:
    paths = sorted(download_dir.rglob("*.pdf"))

    moved = 0
    for path in paths:
        month_stem = _month_stem_from_name(path.name)
        target_name = f"{month_stem}.pdf"
        fy_dir = download_dir / _fy_folder_name(month_stem)
        fy_dir.mkdir(parents=True, exist_ok=True)
        target = fy_dir / target_name
        if target.exists() and target.resolve() != path.resolve():
            target = unique_path(fy_dir, target_name)
        if path.resolve() == target.resolve():
            continue
        old_path = path
        _ = path.rename(target)
        print(f"organized: {old_path} -> {target}")
        moved += 1
    return moved


def rename_pdfs(download_dir: Path) -> int:
    renamed = 0
    for path in sorted(download_dir.glob("*.pdf")):
        target_name = f"{_month_stem_from_name(path.name)}.pdf"
        if path.name == target_name:
            continue
        target = download_dir / target_name
        if target.exists() and target.resolve() != path.resolve():
            target = unique_path(download_dir, target_name)
        if path.resolve() == target.resolve():
            continue
        old_name = path.name
        _ = path.rename(target)
        print(f"renamed: {old_name} -> {target.name}")
        renamed += 1
    return renamed


def main(download_dir: Path | None = None) -> None:
    settings = load_settings()
    if download_dir is None:
        if len(sys.argv) > 1:
            download_dir = Path(sys.argv[1])
        else:
            download_dir = settings.download_path

    if not download_dir.is_dir():
        print(f"error: download directory not found: {download_dir}", file=sys.stderr)
        sys.exit(1)

    password = require_pdf_password(settings)

    print(f"cleanup: {download_dir}")
    print()

    removed = prune_non_pdfs(download_dir)
    decrypted = decrypt_pdfs_in_place(download_dir, password)
    deleted = dedupe_pdfs(download_dir)
    renamed = rename_pdfs(download_dir)
    organized = organize_by_financial_year(download_dir)

    print()
    print(
        f"done: {removed} non-pdf removed, {decrypted} decrypted, {deleted} duplicate(s) removed, "
        + f"{renamed} renamed, {organized} moved into FY folder(s)"
    )


if __name__ == "__main__":
    main()
