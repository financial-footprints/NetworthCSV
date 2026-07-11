"""Shared helpers for opening and reading password-protected PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf.errors import PdfReadError

from networthcsv.errors import StageError


def extract_pdf_text_plumber(path: Path, passwords: list[str]) -> str:
    candidates: list[str | None] = [None, *passwords]
    last_error: Exception | None = None

    for password in candidates:
        try:
            if password is None:
                pdf_context = pdfplumber.open(str(path))
            else:
                pdf_context = pdfplumber.open(str(path), password=password)
            with pdf_context as pdf:
                pages: list[str] = []
                for page in pdf.pages:
                    text = page.extract_text(layout=True)
                    if text:
                        pages.append(text)
                return "\n\n".join(pages)
        except (PdfReadError, OSError, ValueError) as exc:
            last_error = exc
            continue

    detail = f": {last_error}" if last_error is not None else ""
    raise StageError(f"could not open {path}{detail}")
