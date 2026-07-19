"""Shared email message filtering and attachment extraction."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import cast

from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from networthcsv.utils.path import unique_path
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.zip_archive import (
    ZipArchiveError,
    extract_csvs_from_zip,
    sanitize_zip_member_name,
)

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CHARSET_ALIASES: dict[str, str] = {
    "unknown-8bit": "latin-1",
    "unknown": "latin-1",
    "x-unknown": "latin-1",
    "default": "utf-8",
}


def _charset_for_decode(charset: str | None) -> str:
    if not charset:
        return "utf-8"
    key = charset.lower().strip()
    return _CHARSET_ALIASES.get(key, charset)


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    header_parts = cast(
        list[tuple[bytes | str, str | None]],
        decode_header(value),
    )
    for fragment, charset in header_parts:
        if isinstance(fragment, bytes):
            enc = _charset_for_decode(charset)
            try:
                parts.append(fragment.decode(enc, errors="replace"))
            except LookupError:
                parts.append(fragment.decode("latin-1", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts)


def subject_matches(msg: Message, subjects: list[str]) -> bool:
    decoded = decode_mime_header(msg.get("Subject"))
    lowered = decoded.lower()
    return any(subject.lower() in lowered for subject in subjects)


def _decode_part_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, (bytes, bytearray)):
        return ""
    charset = part.get_content_charset()
    enc = _charset_for_decode(charset)
    try:
        return bytes(payload).decode(enc, errors="replace")
    except LookupError:
        return bytes(payload).decode("latin-1", errors="replace")


def extract_message_body(msg: Message) -> str:
    parts: list[str] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        if not part.get_content_type().startswith("text/"):
            continue
        text = _decode_part_payload(part)
        if text:
            parts.append(text)
    return "\n".join(parts)


def body_matches(msg: Message, body_contains: list[str]) -> bool:
    if not body_contains:
        return True
    haystack_parts = [extract_message_body(msg), *_attachment_filenames(msg)]
    lowered = "\n".join(haystack_parts).lower()
    return any(body.lower() in lowered for body in body_contains if body)


def parse_from_addresses(msg: Message) -> list[tuple[str, str]]:
    decoded = decode_mime_header(msg.get("From"))
    addresses: list[tuple[str, str]] = []
    for _name, addr in getaddresses([decoded]):
        if not addr or "@" not in addr:
            continue
        local, domain = addr.rsplit("@", 1)
        addresses.append((local.lower(), domain.lower()))
    return addresses


def from_matches(msg: Message, from_filters: list[str]) -> bool:
    if not from_filters:
        return True
    addresses = parse_from_addresses(msg)
    if not addresses:
        return False
    for entry in from_filters:
        if "@" in entry:
            for local, domain in addresses:
                if f"{local}@{domain}" == entry:
                    return True
        else:
            for _local, domain in addresses:
                if domain == entry:
                    return True
    return False


def message_received_datetime(msg: Message) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def _message_month_start(msg: Message) -> date | None:
    dt = message_received_datetime(msg)
    if dt is None:
        return None
    return date(dt.year, dt.month, 1)


def message_in_date_range(
    msg: Message,
    start_date: date | None,
    end_date: date | None,
) -> bool:
    msg_month = _message_month_start(msg)
    if msg_month is None:
        return False
    if start_date is not None:
        range_start = date(start_date.year, start_date.month, 1)
        if msg_month < range_start:
            return False
    if end_date is not None:
        range_end = date(end_date.year, end_date.month, 1)
        if msg_month > range_end:
            return False
    return True


def is_attachment_part(part: Message) -> bool:
    disposition = part.get_content_disposition()
    filename = part.get_filename()
    if disposition == "attachment":
        return True
    if filename and disposition != "inline":
        return True
    return False


def iter_attachment_parts(msg: Message):
    if not msg.is_multipart():
        return
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if is_attachment_part(part):
            yield part


_PDF_MAGIC = b"%PDF"


def is_annual_email(msg: Message) -> bool:
    """True when subject or body mentions annual or year-end statements."""
    subject = decode_mime_header(msg.get("Subject")).lower()
    if "annual" in subject or "year end" in subject:
        return True
    body = extract_message_body(msg).lower()
    return "annual" in body or "year end" in body


def _payload_is_pdf(payload: bytes | bytearray) -> bool:
    return bytes(payload).startswith(_PDF_MAGIC)


def is_pdf_attachment_part(part: Message, *, allow_octet_stream: bool = False) -> bool:
    if not is_attachment_part(part):
        return False
    filename = part.get_filename()
    if filename and Path(sanitize_filename(filename)).suffix.lower() == ".pdf":
        return True
    content_type = part.get_content_type()
    if "/" not in content_type:
        return False
    maintype, subtype = content_type.split("/", 1)
    if maintype == "application" and subtype.lower() == "pdf":
        return True
    if (
        allow_octet_stream
        and maintype == "application"
        and subtype.lower()
        in {
            "octet-stream",
            "x-download",
        }
    ):
        payload = part.get_payload(decode=True)
        return isinstance(payload, (bytes, bytearray)) and _payload_is_pdf(payload)
    return False


def is_csv_attachment_part(part: Message) -> bool:
    if not is_attachment_part(part):
        return False
    filename = part.get_filename()
    if filename and Path(sanitize_filename(filename)).suffix.lower() == ".csv":
        return True
    content_type = part.get_content_type()
    if "/" not in content_type:
        return False
    maintype, subtype = content_type.split("/", 1)
    if maintype == "text" and subtype.lower() == "csv":
        return True
    if maintype == "application" and subtype.lower() in {"csv", "vnd.ms-excel"}:
        return True
    return False


def iter_pdf_attachment_parts(msg: Message):
    annual = is_annual_email(msg)
    for part in iter_attachment_parts(msg):
        if is_pdf_attachment_part(part, allow_octet_stream=annual):
            yield part


def iter_csv_attachment_parts(msg: Message):
    for part in iter_attachment_parts(msg):
        if is_csv_attachment_part(part):
            yield part


def is_zip_attachment_part(part: Message) -> bool:
    if not is_attachment_part(part):
        return False
    filename = part.get_filename()
    if filename and Path(sanitize_filename(filename)).suffix.lower() == ".zip":
        return True
    content_type = part.get_content_type()
    if "/" not in content_type:
        return False
    maintype, subtype = content_type.split("/", 1)
    if maintype == "application" and subtype.lower() in {
        "zip",
        "x-zip-compressed",
        "octet-stream",
    }:
        return (
            filename is not None
            and Path(sanitize_filename(filename)).suffix.lower() == ".zip"
        )
    return False


def iter_zip_attachment_parts(msg: Message):
    for part in iter_attachment_parts(msg):
        if is_zip_attachment_part(part):
            yield part


def _attachment_filenames(msg: Message) -> list[str]:
    names: list[str] = []
    for part in iter_attachment_parts(msg):
        raw = part.get_filename()
        if raw:
            names.append(decode_mime_header(raw))
    return names


def sanitize_filename(name: str) -> str:
    name = decode_mime_header(name)
    name = Path(name).name.strip() or "attachment"
    name = _UNSAFE_CHARS.sub("_", name)
    return name or "attachment"


def download_filename_for_attachment(
    msg: Message,
    attachment_filename: str,
    *,
    annual: bool = False,
) -> str:
    original = sanitize_filename(attachment_filename)
    suffix = Path(original).suffix
    if suffix.lower() == ".pdf":
        suffix = ".pdf"
    elif suffix.lower() == ".csv":
        suffix = ".csv"
    dt = message_received_datetime(msg)
    if dt is not None:
        stem = dt.strftime("%Y-%m-%d")
    else:
        stem = "unknown-date"
    if not suffix and is_annual_email(msg):
        suffix = ".pdf"
    if annual and suffix == ".csv":
        stem = f"{stem}__annual"
    return f"{stem}{suffix}" if suffix else stem


def download_filename_for_extracted_csv(
    msg: Message,
    inner_name: str,
    *,
    annual: bool = False,
) -> str:
    dt = message_received_datetime(msg)
    if dt is not None:
        stem = dt.strftime("%Y-%m-%d")
    else:
        stem = "unknown-date"
    safe_inner = sanitize_zip_member_name(inner_name)
    if annual:
        stem = f"{stem}__annual"
    return f"{stem}__{safe_inner}"


def save_attachments(
    msg: Message,
    download_dir: Path,
    folder_prefix: str,
    account: ResolvedAccount,
) -> int:
    saved = 0
    prefix = f"{folder_prefix}__" if folder_prefix else ""
    annual = is_annual_email(msg)
    subject = decode_mime_header(msg.get("Subject"))

    attachment_parts: list[tuple[Message, str]] = [
        (part, part.get_filename() or "attachment.pdf")
        for part in iter_pdf_attachment_parts(msg)
    ]
    attachment_parts.extend(
        (part, part.get_filename() or "attachment.csv")
        for part in iter_csv_attachment_parts(msg)
    )

    for part, filename in attachment_parts:
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            continue
        is_csv = Path(sanitize_filename(filename)).suffix.lower() == ".csv"
        safe_name = download_filename_for_attachment(
            msg, filename, annual=annual and is_csv
        )
        dest = unique_path(download_dir, f"{prefix}{safe_name}")
        _ = dest.write_bytes(bytes(payload))
        date_note = " (no Date header)" if safe_name.startswith("unknown-date") else ""
        logger.info("saved: %s%s  (subject: %s)", dest, date_note, subject[:80])
        saved += 1

    for part in iter_zip_attachment_parts(msg):
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            continue
        zip_name = part.get_filename() or "attachment.zip"
        try:
            extracted = extract_csvs_from_zip(bytes(payload), account.passwords)
        except ZipArchiveError as exc:
            logger.warning(
                "skip zip attachment %s (subject: %s): %s",
                sanitize_filename(zip_name),
                subject[:80],
                exc,
            )
            continue
        for item in extracted:
            safe_name = download_filename_for_extracted_csv(
                msg,
                item.inner_name,
                annual=annual,
            )
            dest = unique_path(download_dir, f"{prefix}{safe_name}")
            _ = dest.write_bytes(item.content)
            date_note = (
                " (no Date header)" if safe_name.startswith("unknown-date") else ""
            )
            logger.info(
                "saved from zip: %s%s  (subject: %s)",
                dest,
                date_note,
                subject[:80],
            )
            saved += 1

    return saved


def message_headers_match_account(
    msg: Message,
    account: ResolvedAccount,
    start_date: date | None,
    end_date: date | None = None,
) -> bool:
    """Filter using Subject/From/Date only (safe for HEADER-only IMAP fetches)."""
    subject = decode_mime_header(msg.get("Subject"))[:80]
    if not subject_matches(msg, account.mail.subjects):
        logger.debug("skip email (subject): %r", subject)
        return False
    if not from_matches(msg, account.mail.from_addresses):
        logger.debug("skip email (from): %r", subject)
        return False
    if not message_in_date_range(msg, start_date, end_date):
        logger.debug("skip email (date range): %r", subject)
        return False
    return True


def message_matches_account(
    msg: Message,
    account: ResolvedAccount,
    start_date: date | None,
    end_date: date | None = None,
) -> bool:
    subject = decode_mime_header(msg.get("Subject"))[:80]
    if not message_headers_match_account(msg, account, start_date, end_date):
        return False
    has_pdf = bool(list(iter_pdf_attachment_parts(msg)))
    has_csv = bool(list(iter_csv_attachment_parts(msg)))
    has_zip = bool(list(iter_zip_attachment_parts(msg)))
    if not has_pdf and not has_csv and not has_zip:
        logger.debug("skip email (no pdf/csv/zip attachment): %r", subject)
        return False
    if not body_matches(msg, account.mail.body_contains):
        logger.debug(
            "skip email (body_contains %r): %r",
            account.mail.body_contains,
            subject,
        )
        return False
    return True
