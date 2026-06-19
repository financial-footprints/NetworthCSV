"""Statement parser tests."""

from __future__ import annotations

import unittest

from src.parsers.statement import parse_statement_text


class ParseStatementTextTests(unittest.TestCase):
    def test_empty_text_returns_no_rows(self) -> None:
        self.assertEqual(parse_statement_text("   ", source_file="empty.txt"), [])

    def test_non_empty_text_stub_returns_no_rows(self) -> None:
        self.assertEqual(
            parse_statement_text("some statement lines\n", source_file="2024-01.txt"),
            [],
        )


if __name__ == "__main__":
    _ = unittest.main()
