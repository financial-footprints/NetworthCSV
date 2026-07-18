"""Shared helpers for parse-stage integration tests."""

from __future__ import annotations

import csv
from pathlib import Path

from cleanup_support import run_context
from networthcsv.pipeline.parse.parse import run
from networthcsv.pipeline.results import ParseAccountResult
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.path import account_fy_dir, fy_folder_name, transactions_csv_name


def statement_fy_dir(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
) -> Path:
    return account_fy_dir(download_path, account, fy_folder_name(period_stem))


def write_statement_pair(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
    txt_text: str,
) -> Path:
    fy_dir = statement_fy_dir(download_path, account, period_stem)
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    _ = (fy_dir / f"{period_stem}.pdf").write_bytes(b"%PDF")
    _ = (fy_dir / f"{period_stem}.txt").write_text(txt_text, encoding="utf-8")
    return fy_dir


def write_statement_csv(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
    csv_text: str,
) -> Path:
    fy_dir = statement_fy_dir(download_path, account, period_stem)
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    csv_path = fy_dir / f"{period_stem}.csv"
    _ = csv_path.write_text(csv_text, encoding="utf-8")
    return csv_path


def run_parse(
    download_path: Path,
    account: ResolvedAccount,
) -> ParseAccountResult:
    return run(account, run_context(download_path))


def transactions_output_path(fy_dir: Path, period_stem: str) -> Path:
    return fy_dir / transactions_csv_name(period_stem)


def read_transactions_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
