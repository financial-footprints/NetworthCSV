"""Helpers for building ZIP fixtures in tests."""

from __future__ import annotations

import io
import zipfile

import pyzipper


def build_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def build_aes_zip(entries: dict[str, bytes], password: str) -> bytes:
    buffer = io.BytesIO()
    pwd_bytes = password.encode("utf-8")
    with pyzipper.AESZipFile(
        buffer,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(pwd_bytes)
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()
