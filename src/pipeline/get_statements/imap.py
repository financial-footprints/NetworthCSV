"""Extract statement attachments via read-only IMAP."""

from __future__ import annotations

import email
from datetime import date
from email.message import Message

from src.context import RunContext
from src.utils.email.email_message import (
    message_matches_account,
    sanitize_filename,
    save_attachments,
)
from src.utils.email.readonly_imap import ReadOnlyImapClient, parse_uid_search_response
from src.settings import EmailSource, EmailSourceSettings, ResolvedAccount, account_download_path


def _escape_gmail_term(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _gmail_after_clause(start_date: date | None) -> str:
    if start_date is None:
        return ""
    return f" after:{start_date.year:04d}/{start_date.month:02d}/{start_date.day:02d}"


def build_gmail_raw_query(subjects: list[str], start_date: date | None) -> str:
    subject_terms = " OR ".join(
        f'subject:"{_escape_gmail_term(subject)}"' for subject in subjects
    )
    after_clause = _gmail_after_clause(start_date)
    return f"has:attachment ({subject_terms}){after_clause}"


def _imap_since_clause(start_date: date | None) -> str:
    if start_date is None:
        return ""
    return start_date.strftime("%d-%b-%Y")


def build_imap_search_criteria(
    subjects: list[str],
    start_date: date | None,
    *,
    host: str,
) -> tuple[str | None, tuple[str, ...]]:
    """Return (charset, criteria parts) for IMAP SEARCH or UID SEARCH."""
    if host.rstrip(".").endswith("gmail.com"):
        query = build_gmail_raw_query(subjects, start_date)
        return None, ("X-GM-RAW", query)

    criteria: list[str] = []
    if start_date is not None:
        criteria.extend(["SINCE", _imap_since_clause(start_date)])

    if len(subjects) == 1:
        criteria.extend(["SUBJECT", subjects[0]])
    else:
        or_parts: list[str] = []
        for subject in reversed(subjects):
            if len(or_parts) == 0:
                or_parts = ["SUBJECT", subject]
            else:
                or_parts = ["OR", "SUBJECT", subject, *or_parts]
        criteria.extend(or_parts)

    return "UTF-8", tuple(criteria)


_ImapFetchItem = bytes | tuple[bytes, bytes | None] | None


def _message_from_fetch_data(data: list[_ImapFetchItem]) -> Message | None:
    for item in data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        payload = item[1]
        if isinstance(payload, bytes) and payload:
            return email.message_from_bytes(payload)
    return None


def fetch_message(client: ReadOnlyImapClient, uid: str) -> Message | None:
    typ, data = client.uid_fetch(uid, "(BODY.PEEK[])")
    if typ != "OK" or not data:
        return None
    return _message_from_fetch_data(data)


def print_run_settings(
    email_settings: EmailSourceSettings,
    subjects: list[str],
    from_filters: list[str],
    bodies: list[str],
    download_dir: object,
    start_date: date | None,
    *,
    bank: str | None = None,
) -> None:
    print("settings:")
    if bank:
        print(f"  bank:          {bank}")
    print(f"  host:          {email_settings.host}")
    print(f"  folder:        {email_settings.folder}")
    print(f"  username:      {email_settings.username}")
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


def run_account(
    client: ReadOnlyImapClient,
    ctx: RunContext,
    account: ResolvedAccount,
    *,
    email_settings: EmailSourceSettings,
    folder_label: str,
) -> None:
    download_dir = account_download_path(ctx.settings, account)
    _ = download_dir.mkdir(parents=True, exist_ok=True)

    print_run_settings(
        email_settings,
        account.subjects,
        account.from_filters,
        account.bodies,
        download_dir,
        ctx.settings.start_date,
        bank=account.bank,
    )
    print()

    charset, criteria = build_imap_search_criteria(
        account.subjects,
        ctx.settings.start_date,
        host=email_settings.host,
    )
    typ, data = client.search(charset, *criteria)
    if typ != "OK":
        raise SystemExit(f"error: IMAP search failed: {typ}")

    uids = parse_uid_search_response(data)
    print(f"search: {len(uids)} candidate message(s) in {email_settings.folder}")
    print()

    messages_matched = 0
    attachments_saved = 0
    for uid in uids:
        msg = fetch_message(client, uid)
        if msg is None:
            continue
        if not message_matches_account(msg, account, ctx.settings.start_date):
            continue
        messages_matched += 1
        attachments_saved += save_attachments(msg, download_dir, folder_label)

    print()
    print(
        f"done: {messages_matched} message(s) matched, {attachments_saved} attachment(s) saved to {download_dir}"
    )


def run_imap_extract(ctx: RunContext) -> None:
    source = ctx.settings.source
    if not isinstance(source, EmailSource):
        raise SystemExit("error: IMAP extract requires source.type email")

    email_settings = source.email
    folder_label = sanitize_filename(email_settings.folder)

    client = ReadOnlyImapClient.connect(
        host=email_settings.host,
        port=email_settings.port,
        username=email_settings.username,
        password=email_settings.password,
        use_ssl=email_settings.use_ssl,
    )
    try:
        typ, data = client.examine(email_settings.folder)
        if typ != "OK":
            first = data[0] if data else None
            detail = first.decode(errors="replace") if isinstance(first, bytes) else typ
            raise SystemExit(f"error: could not open IMAP folder {email_settings.folder!r}: {detail}")

        from src.settings import accounts_to_run

        for account in accounts_to_run(ctx.settings):
            run_account(
                client,
                ctx,
                account,
                email_settings=email_settings,
                folder_label=folder_label,
            )
            print()
    finally:
        try:
            _ = client.close()
        except Exception:
            pass
        try:
            _ = client.logout()
        except Exception:
            pass
