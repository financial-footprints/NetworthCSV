"""Shared email message filtering and attachment extraction."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import cast

from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from src.utils.paths import unique_path
from src.settings import ResolvedAccount

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
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        text = _decode_part_payload(part)
        if not text:
            continue
        if content_type == "text/plain":
            plain_parts.append(text)
        elif content_type == "text/html":
            html_parts.append(re.sub(r"<[^>]+>", " ", text))
    parts = plain_parts if plain_parts else html_parts
    return " ".join(parts)


def body_matches(msg: Message, bodies: list[str]) -> bool:
    if not bodies:
        return True
    lowered = extract_message_body(msg).lower()
    return any(body.lower() in lowered for body in bodies)


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


def message_on_or_after(msg: Message, start_date: date | None) -> bool:
    if start_date is None:
        return True
    dt = message_received_datetime(msg)
    if dt is None:
        return False
    return dt.date() >= start_date


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


def sanitize_filename(name: str) -> str:
    name = decode_mime_header(name)
    name = Path(name).name.strip() or "attachment"
    name = _UNSAFE_CHARS.sub("_", name)
    return name or "attachment"


def download_filename_for_attachment(msg: Message, attachment_filename: str) -> str:
    original = sanitize_filename(attachment_filename)
    suffix = Path(original).suffix
    dt = message_received_datetime(msg)
    if dt is not None:
        stem = dt.strftime("%Y-%m-%d")
    else:
        stem = "unknown-date"
    return f"{stem}{suffix}" if suffix else stem


def save_attachments(
    msg: Message,
    download_dir: Path,
    folder_prefix: str,
) -> int:
    saved = 0
    prefix = f"{folder_prefix}__" if folder_prefix else ""
    for part in iter_attachment_parts(msg):
        filename = part.get_filename()
        if not filename:
            continue
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
) -> bool:
    if not subject_matches(msg, account.subjects):
        return False
    if not from_matches(msg, account.from_filters):
        return False
    if not body_matches(msg, account.bodies):
        return False
    if not message_on_or_after(msg, start_date):
        return False
    if not list(iter_attachment_parts(msg)):
        return False
    return True


def process_message(
    msg: Message,
    download_dir: Path,
    folder_prefix: str,
    account: ResolvedAccount,
    start_date: date | None,
) -> int:
    if not message_matches_account(msg, account, start_date):
        return 0
    return save_attachments(msg, download_dir, folder_prefix)
