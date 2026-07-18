"""IDFC WOW transaction parser and parse-stage tests."""

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

_FIXTURES = FIXTURES_ROOT / "idfc" / "wow"


class IdfcWowParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser = get_parser("idfc", "wow")
        cls.account = make_account(
            bank="idfc",
            variant="wow",
            account_number="1234",
            passwords=["x"],
        )
        cls.classic = (_FIXTURES / "classic-2023-08.txt").read_text(encoding="utf-8")
        cls.modern_2025 = (_FIXTURES / "modern-2025-11.txt").read_text(encoding="utf-8")
        cls.modern_2026 = (_FIXTURES / "modern-2026-04.txt").read_text(encoding="utf-8")

    def test_classic_transactions(self) -> None:
        rows = self.parser.parse(
            self.classic,
            account=self.account,
            source_file="2021-06.pdf",
        )
        self.assertEqual(len(rows), 3)
        debits = [row for row in rows if row.debited > 0]
        credits = [row for row in rows if row.credited > 0]
        self.assertEqual(len(debits), 1)
        self.assertEqual(len(credits), 2)
        self.assertEqual(debits[0].debited, Decimal("100.00"))
        self.assertEqual(credits[0].credited, Decimal("250.00"))

    def test_modern_2025_transactions(self) -> None:
        rows = self.parser.parse(
            self.modern_2025,
            account=self.account,
            source_file="2021-11.pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].debited, Decimal("100.00"))

    def test_modern_2026_transactions(self) -> None:
        rows = self.parser.parse(
            self.modern_2026,
            account=self.account,
            source_file="2021-06.pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].debited, Decimal("100.00"))


class IdfcParseStageTests(unittest.TestCase):
    def test_writes_transactions_csv_for_monthly_statement(self) -> None:
        text = (_FIXTURES / "classic-2023-08.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="idfc", variant="wow", account_number="1234")
            fy_dir = write_statement_pair(download_path, account, "2023-08", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2023-08")
            self.assertTrue(out.is_file())
            self.assertGreater(result.total_transactions, 0)
            rows = read_transactions_csv(out)
            self.assertGreater(len(rows), 0)


if __name__ == "__main__":
    _ = unittest.main()
