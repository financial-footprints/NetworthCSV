"""Statement parser tests."""

from __future__ import annotations

import unittest

from networthcsv.pipeline.parse.statement import parse_statement_text
from networthcsv.settings import ResolvedAccount


def _account() -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "account_number": "5678",
            "file_markers": "5678",
            "subjects": ["BOB"],
            "bodies": [],
            "from": [],
            "passwords": ["secret"],
        }
    )


class ParseStatementTextTests(unittest.TestCase):
    def test_empty_text_returns_no_rows(self) -> None:
        self.assertEqual(
            parse_statement_text("   ", account=_account(), source_file="empty.txt"),
            [],
        )

    def test_non_empty_text_stub_returns_no_rows(self) -> None:
        self.assertEqual(
            parse_statement_text(
                "some statement lines\n",
                account=_account(),
                source_file="2024-01.txt",
            ),
            [],
        )


if __name__ == "__main__":
    _ = unittest.main()
