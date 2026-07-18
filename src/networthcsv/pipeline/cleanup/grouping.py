"""Month bucketing and PDF/CSV hashing for cleanup."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from networthcsv.pipeline.cleanup.models import MonthGroups
from networthcsv.pipeline.upload import period_from_manual_upload
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.period import (
    PeriodSource,
    resolve_csv_period_key_with_source,
    resolve_period_key_with_source,
)
from networthcsv.utils.banks.helpers.jupiter import uses_edge_color_extract
from networthcsv.utils.path import is_csv_path, is_pdf_path, iter_csvs, iter_pdfs
import networthcsv.utils.pdf as pdf


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dedupe_paths_by_hash(
    paths: list[Path],
    *,
    path_hash: dict[Path, str] | None = None,
) -> list[Path]:
    seen: dict[str, Path] = {}
    for path in sorted(paths):
        digest = path_hash.get(path) if path_hash is not None else None
        if digest is None:
            digest = file_hash(path)
        if digest not in seen:
            seen[digest] = path
    return list(seen.values())


def _collect_groups(
    paths: list[Path],
    account: ResolvedAccount,
    *,
    read_raw: Callable[[Path], str],
    resolve_period: Callable[[str, str], tuple[str, PeriodSource]],
) -> MonthGroups:
    by_month: dict[str, list[Path]] = {}
    raw_by_path: dict[Path, str] = {}
    path_month: dict[Path, str] = {}
    path_hash: dict[Path, str] = {}
    path_period_source: dict[Path, PeriodSource] = {}
    seen: set[str] = set()
    hash_to_raw: dict[str, str] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        digest = file_hash(path)
        path_hash[path] = digest
        raw = hash_to_raw.get(digest)
        if raw is None:
            raw = read_raw(path)
            hash_to_raw[digest] = raw
        raw_by_path[path] = raw
        manual_month = period_from_manual_upload(path.name)
        if manual_month is not None:
            month = manual_month
            source: PeriodSource = "manual"
        else:
            month, source = resolve_period(raw, path.name)
        path_month[path] = month
        path_period_source[path] = source
        by_month.setdefault(month, []).append(path)
    return MonthGroups(
        groups=by_month,
        raw_by_path=raw_by_path,
        path_month=path_month,
        path_hash=path_hash,
        path_period_source=path_period_source,
    )


def _list_staging_pdf_and_csv_paths(
    staging_dir: Path,
    *,
    pdf_paths: list[Path] | None,
    csv_paths: list[Path] | None,
) -> tuple[list[Path], list[Path]]:
    if pdf_paths is not None and csv_paths is not None:
        return pdf_paths, csv_paths
    listed_pdfs: list[Path] = []
    listed_csvs: list[Path] = []
    if staging_dir.is_dir():
        for path in sorted(staging_dir.iterdir(), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            if is_pdf_path(path):
                listed_pdfs.append(path)
            elif is_csv_path(path):
                listed_csvs.append(path)
    return (
        pdf_paths if pdf_paths is not None else listed_pdfs,
        csv_paths if csv_paths is not None else listed_csvs,
    )


def collect_staging_groups(
    staging_dir: Path,
    account: ResolvedAccount,
    *,
    pdf_paths: list[Path] | None = None,
    csv_paths: list[Path] | None = None,
) -> tuple[MonthGroups, MonthGroups]:
    """Bucket staging PDFs and CSVs by period from a single directory listing."""
    resolved_pdfs, resolved_csvs = _list_staging_pdf_and_csv_paths(
        staging_dir,
        pdf_paths=pdf_paths,
        csv_paths=csv_paths,
    )
    annotate_edge = uses_edge_color_extract(account.bank, account.variant)
    pdf_groups = _collect_groups(
        resolved_pdfs,
        account,
        read_raw=lambda path: pdf.extract_pdf_text_plumber(
            path,
            account.passwords,
            annotate_edge_amount_colors=annotate_edge,
        ),
        resolve_period=lambda raw, name: resolve_period_key_with_source(
            raw, name, account=account
        ),
    )
    csv_groups = _collect_groups(
        resolved_csvs,
        account,
        read_raw=lambda path: path.read_text(encoding="utf-8", errors="replace"),
        resolve_period=lambda raw, name: resolve_csv_period_key_with_source(
            raw, name, account=account
        ),
    )
    return pdf_groups, csv_groups


def collect_month_groups(
    staging_dir: Path,
    account: ResolvedAccount,
    *,
    paths: list[Path] | None = None,
) -> MonthGroups:
    pdf_paths = paths if paths is not None else list(iter_pdfs(staging_dir))
    annotate_edge = uses_edge_color_extract(account.bank, account.variant)
    return _collect_groups(
        pdf_paths,
        account,
        read_raw=lambda path: pdf.extract_pdf_text_plumber(
            path,
            account.passwords,
            annotate_edge_amount_colors=annotate_edge,
        ),
        resolve_period=lambda raw, name: resolve_period_key_with_source(
            raw, name, account=account
        ),
    )


def collect_csv_groups(
    staging_dir: Path,
    account: ResolvedAccount,
    *,
    paths: list[Path] | None = None,
) -> MonthGroups:
    csv_paths = paths if paths is not None else list(iter_csvs(staging_dir))
    return _collect_groups(
        csv_paths,
        account,
        read_raw=lambda path: path.read_text(encoding="utf-8", errors="replace"),
        resolve_period=lambda raw, name: resolve_csv_period_key_with_source(
            raw, name, account=account
        ),
    )
