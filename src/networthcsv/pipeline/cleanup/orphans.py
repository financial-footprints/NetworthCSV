"""Orphan canonical file sweep."""

from __future__ import annotations

import logging

from networthcsv.settings import AppSettings, ResolvedAccount
from networthcsv.utils.path import (
    discover_account_fy_dirs,
    iter_pdfs,
    pdf_path_for_txt,
    txt_path_for_pdf,
)

logger = logging.getLogger(__name__)


def sweep_orphans(settings: AppSettings, account: ResolvedAccount) -> int:
    removed = 0
    for account_fy_dir in discover_account_fy_dirs(settings.download_path, account):
        for pdf_path in iter_pdfs(account_fy_dir):
            txt_path = txt_path_for_pdf(pdf_path)
            if txt_path.is_file():
                continue
            _ = pdf_path.unlink()
            logger.debug("removed (orphan pdf): %s", pdf_path)
            removed += 1
        for txt_path in sorted(account_fy_dir.glob("*.txt")):
            if txt_path.name == "transactions.csv":
                continue
            pdf_path = pdf_path_for_txt(txt_path)
            if pdf_path.is_file():
                continue
            _ = txt_path.unlink()
            logger.debug("removed (orphan txt): %s", txt_path)
            removed += 1
    return removed
