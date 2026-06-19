#!/usr/bin/env python3
"""
Extract attachments from Thunderbird profile mbox folders by subject.

Configure via app.config.json and user.config.json (see src/settings.py). Override app config with CCPARSER_CONFIG.
Close Thunderbird before running against a live profile path.
"""

from __future__ import annotations

import logging
import mailbox
import re
from datetime import date, datetime
from pathlib import Path
from typing import cast
from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from src.context import RunContext
from src.core.paths import unique_path
from src.settings import ResolvedAccount, account_download_path

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SKIP_DIR_NAMES = frozenset({"Feeds", "smart mailboxes"})
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
    subjects: list[str],
    from_filters: list[str],
    bodies: list[str],
    download_dir: Path,
    folder_prefix: str,
    start_date: date | None,
) -> tuple[int, int]:
    messages_matched = 0
    attachments_saved = 0
    try:
        mbox = mailbox.mbox(str(mbox_path), create=False)
    except OSError as exc:
        logger.warning("could not open %s: %s", mbox_path, exc)
        return 0, 0

    for msg in mbox:
        if not subject_matches(msg, subjects):
            continue
        if not from_matches(msg, from_filters):
            continue
        if not body_matches(msg, bodies):
            continue
        if not message_on_or_after(msg, start_date):
            continue
        if not list(iter_attachment_parts(msg)):
            continue
        messages_matched += 1
        attachments_saved += save_attachments(msg, download_dir, folder_prefix)

    return messages_matched, attachments_saved


def print_run_settings(
    profile: Path,
    subjects: list[str],
    from_filters: list[str],
    bodies: list[str],
    download_dir: Path,
    start_date: date | None,
    mbox: Path | None,
    mbox_count: int,
    bank: str | None = None,
) -> None:
    print("settings:")
    if bank:
        print(f"  bank:          {bank}")
    print(f"  profile:       {profile}")
    print(f"  subjects:      {subjects!r}")
    if from_filters:
        print(f"  from:          {from_filters!r}")
    if bodies:
        print(f"  bodies:        {bodies!r}")
    print(f"  download_path: {download_dir}")
    if start_date is None:
        print("  start_date:    (all emails)")
    else:
        print(f"  start_date:    {start_date.isoformat()}")
    if mbox:
        print(f"  mbox:          {mbox}")
    else:
        print(f"  mbox stores:   {mbox_count}")


def run(
    profile: Path,
    subjects: list[str],
    from_filters: list[str],
    bodies: list[str],
    download_dir: Path,
    start_date: date | None,
    mbox: Path | None = None,
    *,
    bank: str | None = None,
) -> None:
    if not profile.is_dir():
        raise SystemExit(f"error: profile directory not found: {profile}")

    _ = download_dir.mkdir(parents=True, exist_ok=True)

    if mbox:
        if not mbox.is_file():
            raise SystemExit(f"error: mbox file not found: {mbox}")
        mbox_files = [mbox]
    else:
        mbox_files = discover_mbox_files(profile)
        if not mbox_files:
            raise SystemExit("error: no mbox stores found")

    print_run_settings(
        profile,
        subjects,
        from_filters,
        bodies,
        download_dir,
        start_date,
        mbox,
        len(mbox_files),
        bank,
    )
    print()

    total_messages = 0
    total_attachments = 0

    for mbox_path in mbox_files:
        folder_label = sanitize_filename(mbox_path.name)
        print(f"scanning: {mbox_path}")
        matched, saved = process_mbox(
            mbox_path,
            subjects,
            from_filters,
            bodies,
            download_dir,
            folder_label,
            start_date,
        )
        if matched:
            print(f"  {matched} message(s), {saved} attachment(s)")
        total_messages += matched
        total_attachments += saved

    print()
    print(
        f"done: {total_messages} message(s) matched, {total_attachments} attachment(s) saved to {download_dir}"
    )


def run_account(ctx: RunContext, account: ResolvedAccount) -> None:
    run(
        ctx.settings.profile,
        account.subjects,
        account.from_filters,
        account.bodies,
        account_download_path(ctx.settings, account),
        ctx.settings.start_date,
        ctx.settings.mbox,
        bank=account.bank,
    )


def main() -> None:
    from src.cli import run_stage_main

    def run_one(_download_dir: Path, account: ResolvedAccount, ctx: RunContext) -> None:
        run_account(ctx, account)

    run_stage_main(
        run_account=run_one,
        flush_alerts=False,
    )


if __name__ == "__main__":
    main()
