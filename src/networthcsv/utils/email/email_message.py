"""Shared email message filtering and attachment extraction."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import cast

from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from networthcsv.utils.path import unique_path
from networthcsv.settings import ResolvedAccount

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
    return all(body.lower() in lowered for body in body_contains)


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


def is_yearly_email(msg: Message) -> bool:
    decoded = decode_mime_header(msg.get("Subject"))
    return "year end" in decoded.lower()


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


def iter_pdf_attachment_parts(msg: Message):
    yearly = is_yearly_email(msg)
    for part in iter_attachment_parts(msg):
        if is_pdf_attachment_part(part, allow_octet_stream=yearly):
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


def download_filename_for_attachment(msg: Message, attachment_filename: str) -> str:
    original = sanitize_filename(attachment_filename)
    suffix = Path(original).suffix
    if suffix.lower() == ".pdf":
        suffix = ".pdf"
    dt = message_received_datetime(msg)
    if dt is not None:
        stem = dt.strftime("%Y-%m-%d")
    else:
        stem = "unknown-date"
    if not suffix and is_yearly_email(msg):
        suffix = ".pdf"
    return f"{stem}{suffix}" if suffix else stem


def save_attachments(
    msg: Message,
    download_dir: Path,
    folder_prefix: str,
) -> int:
    saved = 0
    prefix = f"{folder_prefix}__" if folder_prefix else ""
    for part in iter_pdf_attachment_parts(msg):
        filename = part.get_filename() or "attachment.pdf"
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            continue
        safe_name = download_filename_for_attachment(msg, filename)
        dest = unique_path(download_dir, f"{prefix}{safe_name}")
        _ = dest.write_bytes(bytes(payload))
        subject = decode_mime_header(msg.get("Subject"))
        date_note = " (no Date header)" if safe_name.startswith("unknown-date") else ""
        print(f"saved: {dest}{date_note}  (subject: {subject[:80]})")
        saved += 1
    return saved


def message_matches_account(
    msg: Message,
    account: ResolvedAccount,
    start_date: date | None,
    end_date: date | None = None,
) -> bool:
    if not subject_matches(msg, account.mail.subjects):
        return False
    if not from_matches(msg, account.mail.from_addresses):
        return False
    if not message_in_date_range(msg, start_date, end_date):
        return False
    if not list(iter_pdf_attachment_parts(msg)):
        return False
    if not body_matches(msg, account.mail.body_contains):
        return False
    return True
