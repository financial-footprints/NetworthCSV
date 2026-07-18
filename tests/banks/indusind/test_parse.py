"""IndusInd transaction parser and parse-stage tests."""

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


class IndusindParserTests(unittest.TestCase):
    def test_parses_auraedge(self) -> None:
        text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        account = make_account(bank="indusind", variant="auraedge")
        rows = get_parser("indusind", "auraedge").parse(
            text, account=account, source_file="2021-02.pdf"
        )
        self.assertEqual(len(rows), 2)
        credits = [row for row in rows if row.credited > 0]
        debits = [row for row in rows if row.debited > 0]
        self.assertEqual(len(credits), 1)
        self.assertEqual(len(debits), 1)
        self.assertEqual(credits[0].credited, Decimal("760.00"))
        self.assertEqual(debits[0].debited, Decimal("10.00"))


class IndusindParseStageTests(unittest.TestCase):
    def test_writes_transactions_csv(self) -> None:
        text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="indusind", variant="auraedge")
            fy_dir = write_statement_pair(download_path, account, "2021-02", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2021-02")
            self.assertTrue(out.is_file())
            self.assertEqual(result.total_transactions, 2)
            self.assertEqual(len(read_transactions_csv(out)), 2)


if __name__ == "__main__":
    _ = unittest.main()
