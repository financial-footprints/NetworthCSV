"""Extract attachments from Thunderbird profile mbox folders by subject.

Configure via app.config.json and user.config.json (see networthcsv.settings). Override app config with NETWORTHCSV_CONFIG.
Close Thunderbird before running against a live profile path.
"""

from __future__ import annotations

import logging
import mailbox
from datetime import date
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.results import ExtractAccountResult
from networthcsv.utils.email.email_message import (
    message_matches_account,
    sanitize_filename,
    save_attachments,
)
from networthcsv.settings import (
    ResolvedAccount,
    ThunderbirdSource,
)
from networthcsv.utils.account_dates import resolve_account_search_dates
from networthcsv.utils.path import account_download_path

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
    end_date: date | None = None,
) -> tuple[int, int]:
    messages_matched = 0
    attachments_saved = 0
    try:
        mbox = mailbox.mbox(str(mbox_path), create=False)
    except OSError as exc:
        logger.warning("could not open %s: %s", mbox_path, exc)
        return 0, 0

    for msg in mbox:
        if not message_matches_account(msg, account, start_date, end_date):
            continue
        messages_matched += 1
        attachments_saved += save_attachments(msg, download_dir, folder_prefix, account)

    return messages_matched, attachments_saved


def extract_account(
    profile: Path,
    account: ResolvedAccount,
    download_dir: Path,
    global_start_date: date | None,
    ctx: RunContext,
) -> ExtractAccountResult:
    if not profile.is_dir():
        raise StageError(f"profile directory not found: {profile}")

    _ = download_dir.mkdir(parents=True, exist_ok=True)

    effective_start, effective_end = resolve_account_search_dates(
        account,
        global_start_date,
    )

    mbox_files = discover_mbox_files(profile)
    if not mbox_files:
        raise StageError("no mbox stores found")

    ctx.reporter.extract_settings(
        bank=account.bank,
        subjects=account.mail.subjects,
        from_filters=account.mail.from_addresses,
        body_contains=account.mail.body_contains,
        download_dir=download_dir,
        start_date=effective_start,
        end_date=effective_end,
        extras=(
            ("profile", str(profile)),
            ("mbox stores", str(len(mbox_files))),
        ),
    )
    ctx.reporter.blank_line()

    total_messages = 0
    total_attachments = 0

    for mbox_path in mbox_files:
        folder_label = sanitize_filename(mbox_path.name)
        ctx.reporter.extract_scanning_mbox(mbox_path)
        matched, saved = process_mbox(
            mbox_path,
            account,
            download_dir,
            folder_label,
            effective_start,
            effective_end,
        )
        ctx.reporter.extract_mbox_progress(matched, saved)
        total_messages += matched
        total_attachments += saved

    result = ExtractAccountResult(
        bank=account.bank,
        download_dir=download_dir,
        messages_matched=total_messages,
        attachments_saved=total_attachments,
    )
    ctx.reporter.extract_account_done(result)
    return result


def run_account(ctx: RunContext, account: ResolvedAccount) -> ExtractAccountResult:
    source = ctx.settings.source
    if not isinstance(source, ThunderbirdSource):
        raise StageError("Thunderbird extract requires source.type thunderbird")

    return extract_account(
        source.thunderbird.profile,
        account,
        account_download_path(ctx.settings.download_path, account),
        ctx.settings.start_date,
        ctx,
    )


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(
        lambda: run_stage_main(
            run_account=run_account,
            flush_alerts=True,
        )
    )


if __name__ == "__main__":
    main()
