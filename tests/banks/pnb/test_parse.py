"""PNB transaction parser and parse-stage tests."""

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


class PnbParserTests(unittest.TestCase):
    def test_parses_platinum(self) -> None:
        text = (FIXTURES_ROOT / "pnb/platinum/sample.txt").read_text(encoding="utf-8")
        account = make_account(bank="pnb", variant="platinum")
        rows = get_parser("pnb", "platinum").parse(
            text, account=account, source_file="2021-05.pdf"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].credited, Decimal("780.00"))
        self.assertEqual(rows[1].debited, Decimal("680.00"))


class PnbParseStageTests(unittest.TestCase):
    def test_writes_transactions_csv(self) -> None:
        text = (FIXTURES_ROOT / "pnb/platinum/sample.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="pnb", variant="platinum")
            fy_dir = write_statement_pair(download_path, account, "2021-05", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2021-05")
            self.assertTrue(out.is_file())
            self.assertEqual(result.total_transactions, 2)
            self.assertEqual(len(read_transactions_csv(out)), 2)


if __name__ == "__main__":
    _ = unittest.main()
