"""Month bucketing and PDF hashing for cleanup."""

from __future__ import annotations

import hashlib
from pathlib import Path

from networthcsv.pipeline.cleanup.models import MonthGroups
from networthcsv.pipeline.upload import period_from_manual_upload
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.period import PeriodSource, resolve_period_key_with_source
from networthcsv.utils.path import iter_pdfs
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


def collect_month_groups(
    staging_dir: Path,
    account: ResolvedAccount,
    *,
    paths: list[Path] | None = None,
) -> MonthGroups:
    by_month: dict[str, list[Path]] = {}
    raw_by_path: dict[Path, str] = {}
    path_month: dict[Path, str] = {}
    path_hash: dict[Path, str] = {}
    path_period_source: dict[Path, PeriodSource] = {}
    seen: set[str] = set()
    hash_to_raw: dict[str, str] = {}
    pdf_paths = paths if paths is not None else list(iter_pdfs(staging_dir))
    for path in sorted(pdf_paths, key=lambda item: item.as_posix()):
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        digest = file_hash(path)
        path_hash[path] = digest
        raw = hash_to_raw.get(digest)
        if raw is None:
            raw = pdf.extract_pdf_text_plumber(path, account.passwords)
            hash_to_raw[digest] = raw
        raw_by_path[path] = raw
        manual_month = period_from_manual_upload(path.name)
        if manual_month is not None:
            month = manual_month
            source: PeriodSource = "manual"
        else:
            month, source = resolve_period_key_with_source(
                raw, path.name, account=account
            )
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
