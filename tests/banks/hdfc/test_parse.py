"""HDFC transaction parser and parse-stage tests."""

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
    write_statement_pair,
)
from networthcsv.pipeline.parse.banks import get_parser

_FIXTURES = FIXTURES_ROOT / "hdfc"


class HdfcParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.account = make_account(
            bank="hdfc",
            variant="swiggy",
            account_number="5678",
            passwords=["x"],
        )

    def test_parses_yearly_sample(self) -> None:
        text = (_FIXTURES / "default/yearly-sample.txt").read_text(encoding="utf-8")
        rows = get_parser("hdfc", "default").parse(
            text,
            account=self.account,
            source_file="2025.pdf",
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].description, "SAMPLE MERCHANT ONE")
        self.assertEqual(rows[0].debited, Decimal("100.00"))
        self.assertEqual(rows[1].credited, Decimal("50.00"))

    def test_parses_swiggy_monthly(self) -> None:
        text = (_FIXTURES / "swiggy/sample.txt").read_text(encoding="utf-8")
        rows = get_parser("hdfc", "swiggy").parse(
            text,
            account=self.account,
            source_file="2021-05.pdf",
        )
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0].date, date(2021, 5, 14))
        self.assertEqual(rows[0].debited, Decimal("180.00"))
        self.assertEqual(rows[0].credited, Decimal("0"))


class HdfcParseStageTests(unittest.TestCase):
    _MONTHLY = """\
                                  Domestic Transactions
       Date    Transaction Description                               Amount (in Rs.)
     14/05/2021 SAMPLE MERCHANT ONE                          180.00
     18/05/2021 PAYMENT RECEIVED                              50.00Cr
"""

    _ANNUAL = """\
Transaction Details - 	Primary Card Holder Name: SAMPLE CARDHOLDER
Date 	Transaction Description 	Amount 	DR/CR 	Card Number
16-May-2024 	SAMPLE MERCHANT ONE 	100.00 	DR 	123456XXXXXX7890
22-May-2024 	PAYMENT RECEIVED 	50.00 	CR 	123456XXXXXX7890
"""

    def test_writes_per_period_transactions_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="hdfc", variant="swiggy", account_number="5678")
            monthly_dir = write_statement_pair(
                download_path, account, "2021-05", self._MONTHLY
            )
            annual_dir = write_statement_pair(
                download_path, account, "2025", self._ANNUAL
            )

            result = run_parse(download_path, account)

            monthly_out = transactions_output_path(monthly_dir, "2021-05")
            annual_out = transactions_output_path(annual_dir, "2025")
            self.assertTrue(monthly_out.is_file())
            self.assertTrue(annual_out.is_file())
            self.assertFalse((monthly_dir / "transactions.csv").exists())
            self.assertGreater(result.total_transactions, 0)
            rows = read_transactions_csv(monthly_out)
            self.assertGreater(len(rows), 0)
            self.assertIn("SAMPLE MERCHANT ONE", rows[0]["Description"])


if __name__ == "__main__":
    _ = unittest.main()
