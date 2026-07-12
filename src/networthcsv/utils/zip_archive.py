"""ZIP archive helpers for extracting statement CSV files."""

from __future__ import annotations

import io
import logging
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import pyzipper

from networthcsv.errors import StageError

logger = logging.getLogger(__name__)

__all__ = [
    "ExtractedCsv",
    "ZipArchiveError",
    "ZipNoCsvError",
    "ZipPasswordError",
    "extract_csvs_from_zip",
    "password_candidates",
    "sanitize_zip_member_name",
]


class ZipArchiveError(StageError):
    """Base error for ZIP archive extraction."""


class ZipPasswordError(ZipArchiveError):
    """Raised when no configured password opens the archive."""


class ZipNoCsvError(ZipArchiveError):
    """Raised when the archive contains no CSV members."""


@dataclass(frozen=True)
class ExtractedCsv:
    inner_name: str
    content: bytes


def sanitize_zip_member_name(name: str) -> str:
    """Return a safe leaf filename for a ZIP member path."""
    normalized = posixpath.normpath(name.replace("\\", "/"))
    parts = PurePosixPath(normalized).parts
    if not parts or normalized in {".", ".."}:
        return "attachment.csv"
    leaf = parts[-1]
    if leaf in {"", ".", ".."}:
        return "attachment.csv"
    return leaf


def _is_safe_zip_member(name: str) -> bool:
    normalized = posixpath.normpath(name.replace("\\", "/"))
    if normalized.startswith("../") or normalized.startswith("/"):
        return False
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        return False
    if parts and parts[0] == "__MACOSX":
        return False
    if any(part.startswith(".") for part in parts):
        return False
    return True


def _is_csv_member(name: str) -> bool:
    return sanitize_zip_member_name(name).lower().endswith(".csv")


def password_candidates(passwords: list[str]) -> list[str]:
    return list(dict.fromkeys(["", *passwords]))


def extract_csvs_from_zip(
    data: bytes,
    passwords: list[str],
) -> list[ExtractedCsv]:
    """Extract CSV members from a ZIP archive, trying account passwords."""
    candidates = password_candidates(passwords)
    last_error: Exception | None = None

    for password in candidates:
        try:
            return _extract_csv_members(data, password)
        except ZipNoCsvError:
            raise
        except (zipfile.BadZipFile, pyzipper.zipfile.BadZipFile) as exc:
            raise ZipArchiveError(f"invalid zip archive: {exc}") from exc
        except RuntimeError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise ZipPasswordError(
            "configured password(s) did not open zip archive "
            "(also tried empty password)"
        ) from last_error
    raise ZipNoCsvError("zip archive contains no csv files")


def _extract_csv_members(data: bytes, password: str) -> list[ExtractedCsv]:
    extracted: list[ExtractedCsv] = []
    pwd_bytes = password.encode("utf-8") if password else None

    with pyzipper.AESZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not _is_safe_zip_member(info.filename):
                logger.debug("skip unsafe zip member: %s", info.filename)
                continue
            if not _is_csv_member(info.filename):
                continue
            if info.flag_bits & 0x1:
                if not password:
                    raise RuntimeError("encrypted zip member requires password")
                archive.setpassword(pwd_bytes)
                content = archive.read(info.filename)
            else:
                content = archive.read(info.filename)
            extracted.append(
                ExtractedCsv(
                    inner_name=sanitize_zip_member_name(info.filename),
                    content=content,
                )
            )

    if not extracted:
        raise ZipNoCsvError("zip archive contains no csv files")
    return extracted
