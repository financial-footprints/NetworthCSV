"""ICICI CSV transaction parser tests."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from cleanup_support import account as make_account
from networthcsv.pipeline.parse.banks import get_parser

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "icici" / "csv"


class IciciCsvParserTests(unittest.TestCase):
    def test_parser_registered_for_icici(self) -> None:
        parser = get_parser("icici", "default")
        self.assertEqual(type(parser).__name__, "IciciStatementParser")

    def test_parses_annual_fixture(self) -> None:
        text = (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        rows = get_parser("icici").parse(
            text,
            account=make_account(
                bank="icici",
                variant="default",
                account_number="7788",
                text_contains=[],
            ),
            source_file="yearly-sample.csv",
        )
        self.assertEqual(len(rows), 9)
        debit = rows[0]
        self.assertEqual(debit.date, date(2024, 4, 11))
        self.assertEqual(debit.debited, Decimal("1763.51"))
        self.assertEqual(debit.credited, Decimal("0"))
        credit = rows[1]
        self.assertEqual(credit.credited, Decimal("1045.00"))
        self.assertEqual(credit.debited, Decimal("0"))

    def test_parses_monthly_fixture(self) -> None:
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        rows = get_parser("icici").parse(
            text,
            account=make_account(
                bank="icici",
                variant="default",
                account_number="7788",
                text_contains=[],
            ),
            source_file="2026-04.csv",
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].ref_no, "99112233440")
        self.assertEqual(rows[0].debited, Decimal("200.00"))

    def test_non_csv_text_returns_empty(self) -> None:
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


if __name__ == "__main__":
    _ = unittest.main()
