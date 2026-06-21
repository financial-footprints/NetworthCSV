"""Shared helpers for opening and reading password-protected PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def open_pdf_reader(path: Path, passwords: list[str]) -> PdfReader:
    reader = PdfReader(str(path))
    if not reader.is_encrypted:
        return reader
    if not passwords:
        raise SystemExit(f"error: encrypted PDF requires password: {path}")
    for password in passwords:
        trial = PdfReader(str(path))
        if trial.decrypt(password) != 0:
            return trial
    raise SystemExit(
        f"error: none of {len(passwords)} password(s) worked for {path}"
    )


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
    raise SystemExit(f"error: could not open {path}{detail}")
