"""Read-only IMAP client tests."""

from __future__ import annotations

import unittest
from unittest import mock

from src.utils.email.readonly_imap import ReadOnlyImapClient


class ReadOnlyImapClientTests(unittest.TestCase):
    def test_uid_fetch_rejects_non_peek_body(self) -> None:
        conn = mock.MagicMock()
        client = ReadOnlyImapClient(conn)
        with self.assertRaises(RuntimeError):
            _ = client.uid_fetch("1", "(BODY[])")

    def test_uid_fetch_allows_body_peek(self) -> None:
        conn = mock.MagicMock()
        uid = mock.Mock()
        conn.uid = uid
        uid.return_value = ("OK", [(b"1 (BODY[] {10}", b"message")])
        client = ReadOnlyImapClient(conn)
        typ, _data = client.uid_fetch("1", "(BODY.PEEK[])")
        self.assertEqual(typ, "OK")
        uid.assert_called_once_with("fetch", "1", "(BODY.PEEK[])")
        self.assertIn("UID FETCH", client.commands)

    def test_examine_uses_readonly_select(self) -> None:
        conn = mock.MagicMock()
        select = mock.Mock()
        conn.select = select
        select.return_value = ("OK", [b"1"])
        client = ReadOnlyImapClient(conn)
        typ, _data = client.examine("INBOX")
        self.assertEqual(typ, "OK")
        select.assert_called_once_with("INBOX", readonly=True)
        self.assertIn("EXAMINE", client.commands)

    def test_search_records_command(self) -> None:
        conn = mock.MagicMock()
        search = mock.Mock()
        conn.search = search
        search.return_value = ("OK", [b"1 2"])
        client = ReadOnlyImapClient(conn)
        _ = client.search("UTF-8", "SUBJECT", "statement")
        search.assert_called_once_with("UTF-8", "SUBJECT", "statement")
        self.assertIn("SEARCH", client.commands)


if __name__ == "__main__":
    _ = unittest.main()
