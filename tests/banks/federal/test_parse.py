"""Federal Bank transaction parser and parse-stage tests."""

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


class FederalParserTests(unittest.TestCase):
    def test_parses_signet(self) -> None:
        text = (FIXTURES_ROOT / "federal/signet/sample.txt").read_text(encoding="utf-8")
        account = make_account(bank="federal", variant="signet")
        rows = get_parser("federal", "signet").parse(
            text, account=account, source_file="2021-04.pdf"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].debited, Decimal("10.00"))
        self.assertEqual(rows[1].credited, Decimal("10.00"))

    def test_parses_edge_with_cr_on_repayment(self) -> None:
        text = (FIXTURES_ROOT / "federal/edge/sample.txt").read_text(encoding="utf-8")
        account = make_account(bank="federal", variant="edge")
        rows = get_parser("federal", "edge").parse(
            text, account=account, source_file="2021-01.pdf"
        )
        self.assertEqual(len(rows), 4)
        repayment = next(row for row in rows if "Repayment" in row.description)
        self.assertEqual(repayment.credited, Decimal("830"))
        self.assertEqual(repayment.debited, Decimal("0"))


class FederalParseStageTests(unittest.TestCase):
    def test_writes_signet_transactions_csv(self) -> None:
        text = (FIXTURES_ROOT / "federal/signet/sample.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="federal", variant="signet")
            fy_dir = write_statement_pair(download_path, account, "2021-04", text)

            result = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2021-04")
            self.assertTrue(out.is_file())
            self.assertEqual(result.total_transactions, 2)
            self.assertEqual(len(read_transactions_csv(out)), 2)


if __name__ == "__main__":
    _ = unittest.main()
