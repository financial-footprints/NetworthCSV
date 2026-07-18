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
                "bank": "unknown-bank",
                "account_number": "1",
                "passwords": ["x"],
                "opening_date": "01-01-2020",
                "mail": {"subjects": ["stmt"]},
                "statement": {"text_contains": ["1"]},
            }
        )
        parser = get_parser("unknown-bank")
        rows = parser.parse("line one", account=account, source_file="2024-01.txt")
        self.assertEqual(rows, [])

    def test_known_banks_are_registered(self) -> None:
        for bank, variant in (
            ("hdfc", "swiggy"),
            ("icici", "amazon"),
            ("idfc", "wow"),
            ("indusind", "auraedge"),
            ("bob", "easy"),
            ("yes", "ace"),
            ("pnb", "platinum"),
            ("federal", "edge"),
            ("csb", "edge"),
        ):
            parser = get_parser(bank, variant)
            self.assertNotIsInstance(parser, StubStatementParser)


if __name__ == "__main__":
    _ = unittest.main()
