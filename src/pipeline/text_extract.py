#!/usr/bin/env python3
"""Extract sanitized plain text from statement PDFs into txt/FY*/ folders."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.cli import run_stage_main
from src.core.paths import discover_fy_folders, txt_is_current, txt_path_for_pdf
from src.core.pdf import extract_pdf_text_plumber
from src.settings import AccountSettings, Settings

logger = logging.getLogger(__name__)

_DISALLOWED = re.compile(r"[^A-Za-z0-9 \t\n\r.,/\-:()%&@#*+=<>|_$]")


def sanitize_statement_text(raw: str) -> str:
    cleaned = _DISALLOWED.sub(" ", raw)
    return "\n".join(line.rstrip() for line in cleaned.splitlines())


def process_fy_folder(
    download_dir: Path,
    fy_dir: Path,
    passwords: list[str],
) -> tuple[int, int, int]:
    pdfs = sorted(fy_dir.glob("*.pdf"))
    if not pdfs:
        print(f"skip (no pdfs): {fy_dir}")
        return 0, 0, 0

    written = 0
    skipped = 0
    for pdf_path in pdfs:
        txt_path = txt_path_for_pdf(download_dir, fy_dir, pdf_path)
        if txt_is_current(pdf_path, txt_path):
            print(f"  skip (up to date): {txt_path}")
            skipped += 1
            continue

        raw = extract_pdf_text_plumber(pdf_path, passwords)
        if not raw.strip():
            logger.warning("no text extracted from %s", pdf_path.name)

        txt_path.parent.mkdir(parents=True, exist_ok=True)
        _ = txt_path.write_text(sanitize_statement_text(raw), encoding="utf-8")
        print(f"  wrote: {txt_path}")
        written += 1

    return len(pdfs), written, skipped


def run(download_dir: Path, passwords: list[str], *, bank: str | None = None) -> None:
    if not download_dir.is_dir():
        raise SystemExit(f"error: download directory not found: {download_dir}")

    label = f"{bank} " if bank else ""
    print(f"text_extract: {label}{download_dir}")
    print()

    fy_folders = discover_fy_folders(download_dir)
    if not fy_folders:
        return

    total_pdfs = 0
    total_written = 0
    total_skipped = 0

    for fy_dir in fy_folders:
        print(f"folder: {fy_dir.name}")
        pdf_count, written, skipped = process_fy_folder(download_dir, fy_dir, passwords)
        total_pdfs += pdf_count
        total_written += written
        total_skipped += skipped
        print()

    print(
        f"done: {total_pdfs} pdf(s), {total_written} written, {total_skipped} skipped"
    )


def main() -> None:
    def run_account(download_dir: Path, account: AccountSettings, _: Settings) -> None:
        run(download_dir, account.passwords, bank=account.bank)

    run_stage_main(
        "Extract sanitized plain text from statement PDFs.",
        positional_help="Single account directory (must match a configured {download_path}/{bank}/ path)",
        run_account=run_account,
    )


if __name__ == "__main__":
    main()
