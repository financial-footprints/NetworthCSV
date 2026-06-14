"""Parser tests using anonymized statement text fixtures."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.parsers.bob import BobParser
from src.parsers.idfc import IdfcParser
from src.parsers.pnb import PnbParser

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_bob_parser(self) -> None:
        text = (_FIXTURES / "bob_sample.txt").read_text(encoding="utf-8")
        rows = BobParser().parse_text(text, source_file="2024-03.pdf")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, date(2024, 3, 15))
        self.assertEqual(rows[0].ref_no, "R00935")
        self.assertEqual(rows[0].debited, Decimal("1234.56"))
        self.assertEqual(rows[1].credited, Decimal("500.00"))

    def test_pnb_parser(self) -> None:
        text = (_FIXTURES / "pnb_sample.txt").read_text(encoding="utf-8")
        rows = PnbParser().parse_text(text, source_file="2024-01.pdf")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, date(2024, 1, 15))
        self.assertEqual(rows[0].debited, Decimal("500.00"))
        self.assertEqual(rows[1].credited, Decimal("1200.50"))

    def test_idfc_parser(self) -> None:
        text = (_FIXTURES / "idfc_sample.txt").read_text(encoding="utf-8")
        rows = IdfcParser().parse_text(text, source_file="2024-03.pdf")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, date(2024, 3, 15))
        self.assertEqual(rows[0].debited, Decimal("1234.56"))
        self.assertEqual(rows[1].credited, Decimal("500.00"))

    def test_empty_text_returns_no_rows(self) -> None:
        self.assertEqual(PnbParser().parse_text("   ", source_file="empty.pdf"), [])
        self.assertEqual(BobParser().parse_text("", source_file="empty.pdf"), [])
        self.assertEqual(IdfcParser().parse_text("\n", source_file="empty.pdf"), [])

    def test_no_transactions_warning_path(self) -> None:
        rows = PnbParser().parse_text("no transaction table here", source_file="blank.pdf")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
