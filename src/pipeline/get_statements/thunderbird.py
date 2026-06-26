"""Extract attachments from Thunderbird profile mbox folders by subject.

Configure via app.config.json and user.config.json (see src/settings.py). Override app config with NETWORTHCSV_CONFIG.
Close Thunderbird before running against a live profile path.
"""

from __future__ import annotations

import logging
import mailbox
from datetime import date
from pathlib import Path

from src.context import RunContext
from src.utils.email.email_message import (
    message_matches_account,
    sanitize_filename,
    save_attachments,
)
from src.settings import ResolvedAccount, ThunderbirdSource, account_download_path

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = frozenset({"Feeds", "smart mailboxes"})


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


def process_mbox(
    mbox_path: Path,
    account: ResolvedAccount,
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
        if not message_matches_account(msg, account, start_date):
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
    print(f"  mbox stores:   {mbox_count}")


def run(
    profile: Path,
    account: ResolvedAccount,
    download_dir: Path,
    start_date: date | None,
    *,
    bank: str | None = None,
) -> None:
    if not profile.is_dir():
        raise SystemExit(f"error: profile directory not found: {profile}")

    _ = download_dir.mkdir(parents=True, exist_ok=True)

    mbox_files = discover_mbox_files(profile)
    if not mbox_files:
        raise SystemExit("error: no mbox stores found")

    print_run_settings(
        profile,
        account.subjects,
        account.from_filters,
        account.bodies,
        download_dir,
        start_date,
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
            account,
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
    source = ctx.settings.source
    if not isinstance(source, ThunderbirdSource):
        raise SystemExit("error: Thunderbird extract requires source.type thunderbird")

    run(
        source.thunderbird.profile,
        account,
        account_download_path(ctx.settings, account),
        ctx.settings.start_date,
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
