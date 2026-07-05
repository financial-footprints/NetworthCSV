"""Extract statement attachments via read-only IMAP."""

from __future__ import annotations

import email
from datetime import date
from email.message import Message

from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.results import ExtractAccountResult, ExtractStageResult
from networthcsv.utils.email.email_message import (
    message_matches_account,
    sanitize_filename,
    save_attachments,
)
from networthcsv.utils.email.readonly_imap import (
    ReadOnlyImapClient,
    parse_uid_search_response,
)
from networthcsv.settings import (
    EmailSource,
    EmailSourceSettings,
    ResolvedAccount,
    account_download_path,
    accounts_to_run,
    exclusive_search_end_date,
    resolve_account_search_dates,
)


def _escape_gmail_term(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _gmail_after_clause(start_date: date | None) -> str:
    if start_date is None:
        return ""
    return f" after:{start_date.year:04d}/{start_date.month:02d}/{start_date.day:02d}"


def _gmail_before_clause(end_date: date | None) -> str:
    if end_date is None:
        return ""
    return f" before:{end_date.year:04d}/{end_date.month:02d}/{end_date.day:02d}"


def build_gmail_raw_query(
    subjects: list[str],
    start_date: date | None,
    end_date: date | None = None,
) -> str:
    subject_terms = " OR ".join(
        f'subject:"{_escape_gmail_term(subject)}"' for subject in subjects
    )
    after_clause = _gmail_after_clause(start_date)
    before_clause = _gmail_before_clause(end_date)
    return f"has:attachment ({subject_terms}){after_clause}{before_clause}"


def _imap_since_clause(start_date: date | None) -> str:
    if start_date is None:
        return ""
    return start_date.strftime("%d-%b-%Y")


def _imap_before_clause(end_date: date | None) -> str:
    if end_date is None:
        return ""
    return end_date.strftime("%d-%b-%Y")


def build_imap_search_criteria(
    subjects: list[str],
    start_date: date | None,
    *,
    host: str,
    end_date: date | None = None,
) -> tuple[str | None, tuple[str, ...]]:
    """Return (charset, criteria parts) for IMAP SEARCH or UID SEARCH."""
    if host.rstrip(".").endswith("gmail.com"):
        query = build_gmail_raw_query(subjects, start_date, end_date)
        return None, ("X-GM-RAW", query)

    criteria: list[str] = []
    if start_date is not None:
        criteria.extend(["SINCE", _imap_since_clause(start_date)])
    if end_date is not None:
        criteria.extend(["BEFORE", _imap_before_clause(end_date)])

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


def extract_account(
    client: ReadOnlyImapClient,
    ctx: RunContext,
    account: ResolvedAccount,
    *,
    email_settings: EmailSourceSettings,
    folder_label: str,
) -> ExtractAccountResult:
    download_dir = account_download_path(ctx.settings, account)
    _ = download_dir.mkdir(parents=True, exist_ok=True)

    effective_start, effective_end = resolve_account_search_dates(
        account,
        ctx.settings.start_date,
    )
    search_end = (
        exclusive_search_end_date(effective_end) if effective_end is not None else None
    )

    ctx.reporter.extract_settings(
        bank=account.bank,
        subjects=account.mail.subjects,
        from_filters=account.mail.from_addresses,
        body_contains=account.mail.body_contains,
        download_dir=download_dir,
        start_date=effective_start,
        end_date=effective_end,
        extras=(
            ("host", email_settings.host),
            ("folder", email_settings.folder),
            ("username", email_settings.username),
        ),
    )
    ctx.reporter.blank_line()

    charset, criteria = build_imap_search_criteria(
        account.mail.subjects,
        effective_start,
        host=email_settings.host,
        end_date=search_end,
    )
    typ, data = client.search(charset, *criteria)
    if typ != "OK":
        raise StageError(f"IMAP search failed: {typ}")

    uids = parse_uid_search_response(data)
    ctx.reporter.extract_search(len(uids), email_settings.folder)
    ctx.reporter.blank_line()

    messages_matched = 0
    attachments_saved = 0
    for uid in uids:
        msg = fetch_message(client, uid)
        if msg is None:
            continue
        if not message_matches_account(msg, account, effective_start, effective_end):
            continue
        messages_matched += 1
        attachments_saved += save_attachments(msg, download_dir, folder_label)

    result = ExtractAccountResult(
        bank=account.bank,
        download_dir=download_dir,
        messages_matched=messages_matched,
        attachments_saved=attachments_saved,
    )
    ctx.reporter.extract_account_done(result)
    return result


def run_imap_extract(ctx: RunContext) -> ExtractStageResult:
    source = ctx.settings.source
    if not isinstance(source, EmailSource):
        raise StageError("IMAP extract requires source.type email")

    email_settings = source.email
    folder_label = sanitize_filename(email_settings.folder)

    client = ReadOnlyImapClient.connect(
        host=email_settings.host,
        port=email_settings.port,
        username=email_settings.username,
        password=email_settings.password,
        use_ssl=email_settings.use_ssl,
    )
    results: list[ExtractAccountResult] = []
    try:
        typ, data = client.examine(email_settings.folder)
        if typ != "OK":
            first = data[0] if data else None
            detail = first.decode(errors="replace") if isinstance(first, bytes) else typ
            raise StageError(
                f"could not open IMAP folder {email_settings.folder!r}: {detail}"
            )

        accounts = accounts_to_run(ctx.settings)
        for index, account in enumerate(accounts):
            if index > 0:
                ctx.reporter.blank_line()
            ctx.reporter.account_banner(account, index=index, total=len(accounts))
            results.append(
                extract_account(
                    client,
                    ctx,
                    account,
                    email_settings=email_settings,
                    folder_label=folder_label,
                )
            )
    finally:
        try:
            _ = client.close()
        except Exception:
            pass
        try:
            _ = client.logout()
        except Exception:
            pass

    return ExtractStageResult(accounts=tuple(results))
