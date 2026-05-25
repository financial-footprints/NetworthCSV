#!/usr/bin/env python3
"""
Extract attachments from Thunderbird profile mbox folders by subject.

Configure via extractor.config.json (see src/config.py).
Close Thunderbird before running against a live profile path.

This code is AI generated and not read by a human.
It gets the job done for me and it's not sending any data to the internet.
"""

from __future__ import annotations

import mailbox
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import cast
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime

from src.config import Settings, load_settings

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SKIP_DIR_NAMES = frozenset({"Feeds", "smart mailboxes"})
# Non-standard charsets seen in real mail (e.g. Thunderbird / broken generators)
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


def subject_matches(msg: Message, subject: str) -> bool:
    decoded = decode_mime_header(msg.get("Subject"))
    return subject.lower() in decoded.lower()


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


def message_received_datetime(msg: Message) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def download_filename_for_attachment(msg: Message, attachment_filename: str) -> str:
    original = sanitize_filename(attachment_filename)
    suffix = Path(original).suffix
    dt = message_received_datetime(msg)
    if dt is not None:
        stem = dt.strftime("%Y-%m-%d")
    else:
        stem = "unknown-date"
    return f"{stem}{suffix}" if suffix else stem


def unique_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while True:
        candidate = directory / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def discover_mbox_files(profile: Path) -> list[Path]:
    """Find Thunderbird mbox stores (file with sibling .msf) under ImapMail and Local Folders."""
    found: list[Path] = []
    imap_root = profile / "ImapMail"
    if imap_root.is_dir():
        for path in imap_root.rglob("*"):
            if _is_mbox_store(path):
                found.append(path)

    local_root = profile / "Mail" / "Local Folders"
    if local_root.is_dir():
        for path in local_root.rglob("*"):
            if _is_mbox_store(path):
                found.append(path)

    return sorted(set(found))


def _is_mbox_store(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix == ".msf":
        return False
    if path.name in ("msgFilterRules.dat",):
        return False
    if path.suffix in (".dat", ".json", ".html", ".txt", ".backup"):
        return False
    for part in path.parts:
        if part in _SKIP_DIR_NAMES:
            return False
    msf = path.parent / f"{path.name}.msf"
    return msf.is_file()


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


def process_mbox(
    mbox_path: Path,
    subject: str,
    download_dir: Path,
    folder_prefix: str,
) -> tuple[int, int]:
    messages_matched = 0
    attachments_saved = 0
    try:
        mbox = mailbox.mbox(str(mbox_path), create=False)
    except Exception as exc:
        print(f"warning: could not open {mbox_path}: {exc}", file=sys.stderr)
        return 0, 0

    for msg in mbox:
        if not subject_matches(msg, subject):
            continue
        if not list(iter_attachment_parts(msg)):
            continue
        messages_matched += 1
        attachments_saved += save_attachments(msg, download_dir, folder_prefix)

    return messages_matched, attachments_saved


def print_settings(settings: Settings, mbox_count: int) -> None:
    print("settings:")
    print(f"  profile:       {settings.profile}")
    print(f"  subject:       {settings.subject!r}")
    print(f"  download_path: {settings.download_path}")
    if settings.mbox:
        print(f"  mbox:          {settings.mbox}")
    else:
        print(f"  mbox stores:   {mbox_count}")


def main() -> None:
    settings = load_settings()

    if not settings.profile.is_dir():
        print(f"error: profile directory not found: {settings.profile}", file=sys.stderr)
        sys.exit(1)

    settings.download_path.mkdir(parents=True, exist_ok=True)

    if settings.mbox:
        if not settings.mbox.is_file():
            print(f"error: mbox file not found: {settings.mbox}", file=sys.stderr)
            sys.exit(1)
        mbox_files = [settings.mbox]
    else:
        mbox_files = discover_mbox_files(settings.profile)
        if not mbox_files:
            print("error: no mbox stores found", file=sys.stderr)
            sys.exit(1)

    print_settings(settings, len(mbox_files))
    print()

    total_messages = 0
    total_attachments = 0

    for mbox_path in mbox_files:
        folder_label = sanitize_filename(mbox_path.name)
        print(f"scanning: {mbox_path}")
        matched, saved = process_mbox(
            mbox_path,
            settings.subject,
            settings.download_path,
            folder_label,
        )
        if matched:
            print(f"  {matched} message(s), {saved} attachment(s)")
        total_messages += matched
        total_attachments += saved

    print()
    print(
        f"done: {total_messages} message(s) matched, {total_attachments} attachment(s) saved to {settings.download_path}"
    )


if __name__ == "__main__":
    main()
