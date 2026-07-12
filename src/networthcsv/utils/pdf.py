"""Shared helpers for opening and reading password-protected PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from networthcsv.errors import StageError


def pdf_is_encrypted(path: Path) -> bool:
    try:
        return PdfReader(str(path)).is_encrypted
    except (PdfReadError, PdfStreamError, OSError, ValueError):
        return False


def _open_and_extract(path: Path, password: str | None) -> str:
    if password is None:
        pdf_open = pdfplumber.open(str(path))
    else:
        pdf_open = pdfplumber.open(str(path), password=password)
    with pdf_open as pdf:
        pages: list[str] = []
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                pages.append(text)
        return "\n\n".join(pages)


def extract_pdf_text_plumber(path: Path, passwords: list[str]) -> str:
    if not pdf_is_encrypted(path):
        try:
            return _open_and_extract(path, None)
        except (PdfReadError, OSError, ValueError) as exc:
            raise StageError(f"could not open {path}: {exc}") from exc

    last_error: Exception | None = None
    for password in passwords:
        try:
            return _open_and_extract(path, password)
        except (PdfReadError, PdfminerException, OSError, ValueError) as exc:
            last_error = exc
            continue

    detail = f": {last_error}" if last_error is not None else ""
    raise StageError(f"could not open {path}{detail}")
