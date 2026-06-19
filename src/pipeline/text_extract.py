#!/usr/bin/env python3
"""Extract sanitized plain text from statement PDFs into txt/FY*/ folders."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.alerts.models import Alert, AlertKind
from src.alerts.service import AlertService
from src.context import RunContext
from src.core.paths import (
    discover_fy_folders,
    pdfs_in_fy,
    txt_is_current,
    txt_path_for_pdf,
)
from src.core.pdf import extract_pdf_text_plumber
from src.settings import ResolvedAccount, account_label

logger = logging.getLogger(__name__)

_DISALLOWED = re.compile(r"[^A-Za-z0-9 \n\r.,/\-:()%&@#*+=<>|_$]")


def _normalize_line(line: str) -> str:
    line = line.replace("\t", " ")
    return line.rstrip()


def sanitize_statement_text(raw: str) -> str:
    cleaned = _DISALLOWED.sub(" ", raw)
    return "\n".join(_normalize_line(line) for line in cleaned.split("\n"))


def trim_by_markers(
    raw: str,
    *,
    start_marker: str | None = None,
    end_marker: str | None = None,
) -> str:
    """Keep lines from start_marker through end_marker, inclusive of both marker lines."""
    lines = raw.split("\n")
    start_idx = 0

    if start_marker is not None:
        found = next((i for i, line in enumerate(lines) if start_marker in line), None)
        if found is None:
            logger.debug("start_marker not found: %r", start_marker)
        else:
            start_idx = found

    end_idx = len(lines)
    if end_marker is not None:
        found = next(
            (
                i
                for i, line in enumerate(lines[start_idx:], start=start_idx)
                if end_marker in line
            ),
            None,
        )
        if found is None:
            if any(end_marker in line for line in lines):
                return ""
            logger.debug("end_marker not found: %r", end_marker)
        else:
            end_idx = found + 1

    if start_idx >= end_idx:
        return ""

    return "\n".join(lines[start_idx:end_idx])


def _marker_words(marker: str) -> list[str]:
    return re.sub(r"\s+", " ", marker.strip()).split()


def _information_marker_pattern(marker: str) -> re.Pattern[str]:
    words = _marker_words(marker)
    if not words:
        return re.compile(r"(?!)", re.DOTALL)
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(body, re.DOTALL)


def _drop_blank_lines(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if line.strip())


def _purge_marker_regex(text: str, marker: str) -> str:
    return _information_marker_pattern(marker).sub("", text)


def _start_anchor(words: list[str]) -> str:
    if len(words) <= 6:
        return " ".join(words)
    first = words[0].lstrip("*")
    return " ".join([first, *words[1:5]])


def _purge_marker_line_block(text: str, marker: str) -> str:
    """Remove lines from the first start anchor through the last end anchor."""
    words = _marker_words(marker)
    if not words:
        return text

    if len(words) <= 6:
        start_anchors = [" ".join(words)]
        end_anchor = start_anchors[0]
    else:
        start_anchors = [_start_anchor(words)]
        end_anchor = " ".join(words[-4:])

    lines = text.split("\n")
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and any(anchor in line for anchor in start_anchors):
            start_idx = i
        if start_idx is not None and end_anchor in line:
            end_idx = i

    if start_idx is None or end_idx is None or start_idx > end_idx:
        return text

    return _drop_blank_lines("\n".join(lines[:start_idx] + lines[end_idx + 1 :]))


def purge_information_markers(text: str, *, information_markers: list[str] | None = None) -> str:
    """Remove text matching any information marker from sanitized statement text."""
    if not information_markers:
        return text

    result = text
    for marker in information_markers:
        updated = _purge_marker_regex(result, marker)
        if updated == result:
            updated = _purge_marker_line_block(result, marker)
        if updated == result:
            logger.debug("information marker not matched: %r", marker[:80])
        result = updated

    return _drop_blank_lines(result)


def identifier_present(text: str, identifier: str) -> bool:
    return identifier in text


def check_identifier(
    text: str,
    *,
    identifier: str,
    source_file: str,
    account_label: str,
    alerts: AlertService | None = None,
) -> bool:
    if identifier_present(text, identifier):
        return True
    logger.warning(
        "ignored %s for %s: identifier %r not found",
        source_file,
        account_label,
        identifier,
    )
    if alerts is not None:
        alerts.emit(
            Alert(
                kind=AlertKind.IDENTIFIER_MISSING,
                message=f"identifier {identifier!r} not found in {source_file}",
                account=account_label,
                source_file=source_file,
                identifier=identifier,
            )
        )
    return False


def process_fy_folder(
    download_dir: Path,
    fy_dir: Path,
    account: ResolvedAccount,
    ctx: RunContext,
    *,
    force: bool = False,
) -> tuple[int, int, int, int]:
    pdfs = pdfs_in_fy(download_dir, fy_dir)
    if not pdfs:
        print(f"skip (no pdfs): {fy_dir}")
        return 0, 0, 0, 0

    label = account_label(account)
    written = 0
    skipped = 0
    skipped_identifier = 0
    total = len(pdfs)
    for index, pdf_path in enumerate(pdfs, start=1):
        progress = f"[{index}/{total}]"
        txt_path = txt_path_for_pdf(download_dir, fy_dir, pdf_path)
        if not force and txt_is_current(pdf_path, txt_path):
            print(f"{progress} skip (up to date): {pdf_path.name}", flush=True)
            if not check_identifier(
                txt_path.read_text(encoding="utf-8"),
                identifier=account.identifier,
                source_file=pdf_path.name,
                account_label=label,
                alerts=ctx.alerts,
            ):
                if txt_path.is_file():
                    _ = txt_path.unlink()
                skipped_identifier += 1
            skipped += 1
            continue

        print(f"{progress} extracting: {pdf_path.name}", flush=True)
        raw = extract_pdf_text_plumber(pdf_path, account.passwords)
        if not raw.strip():
            logger.warning("no text extracted from %s", pdf_path.name)
        if not check_identifier(
            raw,
            identifier=account.identifier,
            source_file=pdf_path.name,
            account_label=label,
            alerts=ctx.alerts,
        ):
            if txt_path.is_file():
                _ = txt_path.unlink()
            print(f"{progress} skip (identifier missing): {pdf_path.name}", flush=True)
            skipped_identifier += 1
            continue

        trimmed = trim_by_markers(
            raw,
            start_marker=account.start_marker,
            end_marker=account.end_marker,
        )
        sanitized = sanitize_statement_text(trimmed)
        purged = purge_information_markers(
            sanitized,
            information_markers=account.information_markers,
        )
        _ = txt_path.parent.mkdir(parents=True, exist_ok=True)
        _ = txt_path.write_text(purged, encoding="utf-8")
        print(f"{progress} wrote: {txt_path}", flush=True)
        written += 1

    return len(pdfs), written, skipped, skipped_identifier


def run(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
    if not download_dir.is_dir():
        raise SystemExit(f"error: download directory not found: {download_dir}")

    print(f"text_extract: {account.bank} {download_dir}")
    if ctx.settings.run.force_text_extract:
        print("force: re-extracting all pdfs")
    print()

    fy_folders = discover_fy_folders(download_dir)
    if not fy_folders:
        return

    total_pdfs = 0
    total_written = 0
    total_skipped = 0
    total_skipped_identifier = 0
    force = ctx.settings.run.force_text_extract

    for fy_dir in fy_folders:
        print(f"folder: {fy_dir.name}")
        pdf_count, written, skipped, skipped_identifier = process_fy_folder(
            download_dir,
            fy_dir,
            account,
            ctx,
            force=force,
        )
        total_pdfs += pdf_count
        total_written += written
        total_skipped += skipped
        total_skipped_identifier += skipped_identifier
        print()

    print(
        f"done: {total_pdfs} pdf(s), {total_written} written, {total_skipped} skipped, {total_skipped_identifier} skipped (identifier missing)"
    )


def main() -> None:
    from src.cli import run_stage_main

    def run_account(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
        run(download_dir, account, ctx)

    run_stage_main(run_account=run_account)


if __name__ == "__main__":
    main()
