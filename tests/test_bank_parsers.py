"""Bank parser registry tests."""

from __future__ import annotations

import unittest

from networthcsv.pipeline.parse.banks import get_parser
from networthcsv.pipeline.parse.banks.stub import StubStatementParser
from networthcsv.settings import ResolvedAccount


class BankParserRegistryTests(unittest.TestCase):
    def test_unknown_bank_uses_stub_parser(self) -> None:
        parser = get_parser("unknown-bank")
        self.assertIsInstance(parser, StubStatementParser)

    def test_stub_parser_returns_no_rows_for_non_empty_text(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1",
                "file_markers": "1",
                "subjects": ["stmt"],
                "passwords": ["x"],
            }
        )
        parser = get_parser("bob")
        rows = parser.parse("line one", account=account, source_file="2024-01.txt")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    _ = unittest.main()
