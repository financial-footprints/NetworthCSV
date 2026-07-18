"""CSB transaction parser and parse-stage tests."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cleanup_support import FIXTURES_ROOT, account as make_account
from networthcsv.pipeline.parse.banks import get_parser
from parse_support import (
    read_transactions_csv,
    run_parse,
    transactions_output_path,
    write_statement_pair,
)


class CsbParserTests(unittest.TestCase):
    def test_parses_edge(self) -> None:
        text = (FIXTURES_ROOT / "csb/edge/sample.txt").read_text(encoding="utf-8")
        account = make_account(bank="csb", variant="edge")
        rows = get_parser("csb", "edge").parse(
            text, account=account, source_file="2021-04.pdf"
        )
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row.debited > 0 for row in rows))
        self.assertEqual(rows[0].debited, Decimal("612.40"))


class CsbParseStageTests(unittest.TestCase):
    def test_writes_transactions_csv(self) -> None:
        text = (FIXTURES_ROOT / "csb/edge/sample.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="csb", variant="edge")
            fy_dir = write_statement_pair(download_path, account, "2021-04", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2021-04")
            self.assertTrue(out.is_file())
            self.assertEqual(result.total_transactions, 6)
            self.assertEqual(len(read_transactions_csv(out)), 6)


if __name__ == "__main__":
    _ = unittest.main()
