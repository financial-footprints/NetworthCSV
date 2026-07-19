"""ICICI transaction parser and parse-stage tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from helpers import (
    FIXTURES_ROOT,
    account as make_account,
    read_transactions_csv,
    run_parse,
    transactions_output_path,
    write_statement_csv,
    write_statement_pair,
)
from networthcsv.pipeline.parse.banks import get_parser

_FIXTURES = FIXTURES_ROOT / "icici"
_CSV_FIXTURES = _FIXTURES / "csv"


class IciciParserTests(unittest.TestCase):
    def test_parser_registered(self) -> None:
        parser = get_parser("icici", "default")
        self.assertEqual(type(parser).__name__, "IciciStatementParser")

    def test_parses_annual_csv_fixture(self) -> None:
        text = (_CSV_FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            text_contains=[],
        )
        rows = get_parser("icici").parse(
            text,
            account=account,
            source_file="yearly-sample.csv",
        )
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0].date, date(2024, 4, 11))
        self.assertEqual(rows[0].debited, Decimal("1763.51"))
        self.assertEqual(rows[1].credited, Decimal("1045.00"))

    def test_parses_monthly_csv_fixture(self) -> None:
        text = (_CSV_FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            text_contains=[],
        )
        rows = get_parser("icici").parse(
            text,
            account=account,
            source_file="2026-04.csv",
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].ref_no, "99112233440")

    def test_parses_amazon_txt(self) -> None:
        text = (_FIXTURES / "amazon/sample.txt").read_text(encoding="utf-8")
        account = make_account(bank="icici", variant="amazon")
        rows = get_parser("icici", "amazon").parse(
            text,
            account=account,
            source_file="2021-10.pdf",
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].debited, Decimal("275.50"))
        self.assertEqual(rows[1].credited, Decimal("1380.00"))
        self.assertEqual(rows[1].ref_no, "88472910562")

    def test_non_csv_text_returns_empty_for_csv_only_path(self) -> None:
        rows = get_parser("icici").parse(
            "STATEMENT DATE\nFebruary 12, 2023",
            account=make_account(
                bank="icici",
                variant="default",
                account_number="7788",
                text_contains=[],
            ),
            source_file="2023-02.txt",
        )
        self.assertEqual(rows, [])


class IciciParseStageTests(unittest.TestCase):
    def test_prefers_csv_over_txt_and_keeps_unprocessed(self) -> None:
        csv_body = (
            '"Transaction Details:"\n'
            '"Date","Sr.No.","Transaction Details","Reward Point Header",'
            '"Intl.Amount","Amount(in Rs)","BillingAmountSign"\n'
            '"01-MAY-21","1","SAMPLE STORE","0","0.00","100.00","100.00"\n'
            '"02-MAY-21","2","UPI Payment Received","0","0.00","-50.00","-50.00"\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(
                bank="icici", variant="amazon", account_number="6005"
            )
            fy_dir = write_statement_pair(
                download_path,
                account,
                "2021-05",
                "15/09/2021 1 SHOULD NOT PARSE THIS 999.00\n",
            )
            unprocessed = write_statement_csv(
                download_path, account, "2021-05", csv_body
            )

            _ = run_parse(download_path, account)

            out = transactions_output_path(fy_dir, "2021-05")
            self.assertTrue(out.is_file())
            self.assertTrue(unprocessed.is_file())
            text = out.read_text(encoding="utf-8")
            self.assertIn("SAMPLE STORE", text)
            self.assertNotIn("SHOULD NOT PARSE", text)
            rows = read_transactions_csv(out)
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    _ = unittest.main()
