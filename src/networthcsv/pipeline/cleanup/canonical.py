"""Canonical FY-folder statement output writes."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from networthcsv.pipeline.cleanup.exclusion import statement_should_exclude
from networthcsv.pipeline.cleanup.staging import is_staging_pdf
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.text import statement_text_eligible
from networthcsv.utils.path import (
    iter_statement_csvs,
    iter_statement_pairs,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
)

logger = logging.getLogger(__name__)


def write_txt_atomically(txt_path: Path, content: str) -> None:
    _ = txt_path.parent.mkdir(parents=True, exist_ok=True)
    temp = txt_path.with_suffix(f"{txt_path.suffix}.tmp")
    _ = temp.write_text(content, encoding="utf-8")
    _ = temp.replace(txt_path)


def sanitized_text(raw: str, account: ResolvedAccount) -> str:
    handler = get_handler(account.bank, account.variant)
    return handler.clean_text(raw)


def write_statement_pair(
    staging_dir: Path,
    download_path: Path,
    month: str,
    keeper: Path,
    raw: str,
    account: ResolvedAccount,
) -> None:
    pdf_out = statement_pdf_path(download_path, account, month)
    txt_out = txt_path_for_pdf(pdf_out)
    purged = sanitized_text(raw, account)

    _ = pdf_out.parent.mkdir(parents=True, exist_ok=True)
    if keeper.resolve() != pdf_out.resolve():
        _ = shutil.copy2(keeper, pdf_out)
    write_txt_atomically(txt_out, purged)

    if is_staging_pdf(staging_dir, keeper) and keeper.resolve() != pdf_out.resolve():
        _ = keeper.unlink()
        logger.debug("removed (staging): %s", keeper)

    logger.debug("prepared: %s + %s", pdf_out, txt_out)


def write_statement_csv(
    staging_dir: Path,
    download_path: Path,
    month: str,
    keeper: Path,
    account: ResolvedAccount,
) -> None:
    from networthcsv.pipeline.cleanup.staging import is_staging_csv
    from networthcsv.utils.path import statement_csv_path

    csv_out = statement_csv_path(download_path, account, month)
    _ = csv_out.parent.mkdir(parents=True, exist_ok=True)
    if keeper.resolve() != csv_out.resolve():
        _ = shutil.copy2(keeper, csv_out)

    if is_staging_csv(staging_dir, keeper) and keeper.resolve() != csv_out.resolve():
        _ = keeper.unlink()
        logger.debug("removed (staging csv): %s", keeper)

    logger.debug("prepared csv: %s", csv_out)


def _remove_ineligible_canonical_file(
    path: Path,
    *,
    reason: str,
) -> None:
    if path.is_file():
        _ = path.unlink()
        logger.debug("removed (%s): %s", reason, path)


def remove_ineligible_canonical_outputs(
    download_path: Path,
    account: ResolvedAccount,
) -> int:
    text_contains = account.statement.text_contains
    text_not_contains = account.statement.text_not_contains

    removed = 0
    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        if not pdf_path.is_file() or not txt_path.is_file():
            continue
        if not txt_is_current(pdf_path, txt_path):
            continue
        txt_content = txt_path.read_text(encoding="utf-8")
        if statement_should_exclude(
            txt_content,
            txt_content,
            account=account,
            is_manual=False,
        ):
            _remove_ineligible_canonical_file(pdf_path, reason="excluded statement")
            _remove_ineligible_canonical_file(txt_path, reason="excluded statement")
            removed += 1
            continue
        if statement_text_eligible(
            txt_content,
            text_contains=text_contains,
            text_not_contains=text_not_contains,
            is_manual=False,
        ):
            continue
        _remove_ineligible_canonical_file(pdf_path, reason="ineligible statement")
        _remove_ineligible_canonical_file(txt_path, reason="ineligible statement")
        removed += 1

    for csv_path in iter_statement_csvs(download_path, account):
        if not csv_path.is_file():
            continue
        csv_content = csv_path.read_text(encoding="utf-8")
        if statement_should_exclude(
            csv_content,
            csv_content,
            account=account,
            is_manual=False,
        ):
            _remove_ineligible_canonical_file(csv_path, reason="excluded statement")
            removed += 1
            continue
        if statement_text_eligible(
            csv_content,
            text_contains=text_contains,
            text_not_contains=text_not_contains,
            is_manual=False,
        ):
            continue
        _remove_ineligible_canonical_file(csv_path, reason="ineligible statement")
        removed += 1
    return removed
