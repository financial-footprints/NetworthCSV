"""Read-only IMAP client — only EXAMINE, SEARCH, and BODY.PEEK FETCH."""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from typing import cast

_ALLOWED_COMMAND_PREFIXES = frozenset(
    {
        "LOGIN",
        "AUTHENTICATE",
        "CAPABILITY",
        "EXAMINE",
        "SEARCH",
        "UID",
        "FETCH",
        "CLOSE",
        "LOGOUT",
        "NOOP",
    }
)
_FORBIDDEN_COMMAND_MARKERS = frozenset(
    {
        "STORE",
        "COPY",
        "APPEND",
        "EXPUNGE",
        "DELETE",
        "CREATE",
        "RENAME",
        "MOVE",
    }
)


def _validate_command(name: str) -> None:
    upper = name.upper()
    for marker in _FORBIDDEN_COMMAND_MARKERS:
        if marker in upper:
            raise RuntimeError(f"read-only IMAP client refused command: {name}")


class ReadOnlyImapClient:
    """Thin wrapper over imaplib that only issues read-only IMAP operations."""

    def __init__(self, connection: imaplib.IMAP4) -> None:
        self._conn: imaplib.IMAP4 = connection
        self._commands: list[str] = []

    @property
    def commands(self) -> list[str]:
        return list(self._commands)

    @classmethod
    def connect(
        cls,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
    ) -> ReadOnlyImapClient:
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port)
        else:
            conn = imaplib.IMAP4(host, port)
        client = cls(conn)
        typ, data = client._login(username, password)
        if typ != "OK":
            first = data[0] if data else None
            detail = first.decode(errors="replace") if isinstance(first, bytes) else typ
            raise SystemExit(f"error: IMAP login failed: {detail}")
        return client

    def _record(self, name: str) -> None:
        _validate_command(name)
        self._commands.append(name.upper())

    def _login(self, username: str, password: str) -> tuple[str, list[bytes | None]]:
        self._record("LOGIN")
        return cast(tuple[str, list[bytes | None]], self._conn.login(username, password))

    def examine(self, mailbox: str) -> tuple[str, list[bytes | None]]:
        self._record("EXAMINE")
        return self._conn.select(mailbox, readonly=True)

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes | None]]:
        self._record("SEARCH")
        if charset is None:
            return self._conn.search(None, *criteria)
        return self._conn.search(charset, *criteria)

    def uid_fetch(
        self, uid: str, parts: str
    ) -> tuple[str, list[bytes | tuple[bytes, bytes | None] | None]]:
        if "BODY.PEEK" not in parts.upper() and "RFC822" not in parts.upper():
            raise RuntimeError("read-only IMAP client only allows BODY.PEEK or RFC822 fetch")
        if "BODY[]" in parts.replace(" ", "") and "BODY.PEEK" not in parts.upper():
            raise RuntimeError("read-only IMAP client refused non-PEEK BODY fetch")
        self._record("UID FETCH")
        return self._conn.uid("fetch", uid, parts)

    def close(self) -> tuple[str, list[bytes | None]]:
        self._record("CLOSE")
        return self._conn.close()

    def logout(self) -> tuple[str, list[bytes | None]]:
        self._record("LOGOUT")
        return cast(tuple[str, list[bytes | None]], self._conn.logout())


def parse_uid_search_response(data: Sequence[bytes | None]) -> list[str]:
    if not data or data[0] is None:
        return []
    raw = data[0].decode(errors="replace").strip()
    if not raw:
        return []
    return raw.split()
