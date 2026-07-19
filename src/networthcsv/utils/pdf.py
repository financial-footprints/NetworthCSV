"""Shared helpers for opening and reading password-protected PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from networthcsv.errors import StageError
from networthcsv.utils.banks.helpers.jupiter import annotate_page_text_from_chars


def pdf_is_encrypted(path: Path) -> bool:
    try:
        return PdfReader(str(path)).is_encrypted
    except (PdfReadError, PdfStreamError, OSError, ValueError):
        return False


def _open_and_extract(
    path: Path,
    password: str | None,
    *,
    annotate_edge_amount_colors: bool = False,
) -> str:
    if password is None:
        pdf_open = pdfplumber.open(str(path))
    else:
        pdf_open = pdfplumber.open(str(path), password=password)
    with pdf_open as pdf:
        pages: list[str] = []
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text:
                continue
            if annotate_edge_amount_colors:
                text = annotate_page_text_from_chars(text, page.chars)
            pages.append(text)
        return "\n\n".join(pages)


def extract_pdf_text_plumber(
    path: Path,
    passwords: list[str],
    *,
    annotate_edge_amount_colors: bool = False,
) -> str:
    # Prefer passwords first — most statement PDFs are encrypted.
    last_error: Exception | None = None
    for password in passwords:
        try:
            return _open_and_extract(
                path,
                password,
                annotate_edge_amount_colors=annotate_edge_amount_colors,
            )
        except (PdfReadError, PdfminerException, OSError, ValueError) as exc:
            last_error = exc
            continue

    try:
        return _open_and_extract(
            path,
            None,
            annotate_edge_amount_colors=annotate_edge_amount_colors,
        )
    except (PdfReadError, PdfminerException, OSError, ValueError) as exc:
        last_error = exc

    detail = f": {last_error}" if last_error is not None else ""
    raise StageError(f"could not open {path}{detail}")
