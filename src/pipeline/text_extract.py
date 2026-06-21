#!/usr/bin/env python3
"""Text processing helpers for statement PDFs. Extraction is merged into cleanup."""

from __future__ import annotations

from pathlib import Path

from src.context import RunContext
from src.pipeline.statement_text import (
    check_identifier,
    identifier_present,
    purge_information_markers,
    sanitize_statement_text,
    trim_by_markers,
)
from src.settings import ResolvedAccount

__all__ = [
    "check_identifier",
    "identifier_present",
    "purge_information_markers",
    "sanitize_statement_text",
    "trim_by_markers",
    "run",
    "main",
]


def run(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
    print("note: text_extract is merged into cleanup; running cleanup instead")
    print()
    from src.pipeline.cleanup import run as cleanup_run

    cleanup_run(download_dir, account, ctx)


def main() -> None:
    from src.cli import run_stage_main

    def run_account(download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
        run(download_dir, account, ctx)

    run_stage_main(run_account=run_account)


if __name__ == "__main__":
    main()
