"""BOB transaction parser and parse-stage tests."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from helpers import (
    FIXTURES_ROOT,
    account as make_account,
    read_transactions_csv,
    run_parse,
    transactions_output_path,
    write_statement_pair,
)
from networthcsv.pipeline.parse.banks import get_parser


class BobParserTests(unittest.TestCase):
    def test_parses_easy_format1(self) -> None:
        text = (FIXTURES_ROOT / "bob/easy/format1.txt").read_text(encoding="utf-8")
        account = make_account(bank="bob", variant="easy")
        rows = get_parser("bob", "easy").parse(
            text, account=account, source_file="2024-10.pdf"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].ref_no, "R88001")
        self.assertEqual(rows[0].debited, Decimal("50.00"))
        self.assertIn("MUNICIPAL", rows[0].description)


class BobParseStageTests(unittest.TestCase):
    def test_writes_transactions_csv(self) -> None:
        text = (FIXTURES_ROOT / "bob/easy/format1.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="bob", variant="easy")
            fy_dir = write_statement_pair(download_path, account, "2024-10", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2024-10")
            self.assertTrue(out.is_file())
            self.assertEqual(result.total_transactions, 2)
            self.assertEqual(len(read_transactions_csv(out)), 2)


if __name__ == "__main__":
    _ = unittest.main()
