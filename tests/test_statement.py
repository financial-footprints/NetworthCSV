"""Statement parser tests."""

from __future__ import annotations

import unittest

from helpers import account as make_account
from networthcsv.errors import StageError
from networthcsv.pipeline.parse.statement import parse_statement_text
from networthcsv.settings import ResolvedAccount


class ParseStatementTextTests(unittest.TestCase):
    def test_empty_text_returns_no_rows(self) -> None:
        self.assertEqual(
            parse_statement_text(
                "   ", account=make_account(), source_file="empty.txt"
            ),
            [],
        )

    def test_unknown_bank_raises_stage_error(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "unknown-bank",
                "account_number": "1",
                "passwords": ["x"],
                "opening_date": "01-01-2020",
                "mail": {"subjects": ["stmt"]},
                "statement": {"text_contains": ["1"]},
            }
        )
        with self.assertRaises(StageError):
            _ = parse_statement_text(
                "some statement lines\n",
                account=account,
                source_file="2024-01.txt",
            )


if __name__ == "__main__":
    _ = unittest.main()
