"""Tests for IDFC WOW credit card statement parser."""

from __future__ import annotations

import unittest
from decimal import Decimal

from cleanup_support import FIXTURES_ROOT
from networthcsv.pipeline.parse.banks import get_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler

_FIXTURES = FIXTURES_ROOT / "idfc" / "wow"


def _account() -> ResolvedAccount:
    handler = get_handler("idfc", "wow")
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "idfc",
            "variant": "wow",
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class IdfcWowParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser = get_parser("idfc", "wow")
        cls.account = _account()
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
        self.assertEqual(debits[0].description, "Sample FX Merchant USD, Example")
        self.assertEqual(debits[0].debited, Decimal("100.00"))
        self.assertEqual(credits[0].description, "Online Payment Received")
        self.assertEqual(credits[0].credited, Decimal("250.00"))

    def test_modern_2025_transactions(self) -> None:
        rows = self.parser.parse(
            self.modern_2025,
            account=self.account,
            source_file="2021-11.pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].description, "Sample Merchant One")
        self.assertEqual(rows[0].debited, Decimal("100.00"))

    def test_modern_2026_transactions(self) -> None:
        rows = self.parser.parse(
            self.modern_2026,
            account=self.account,
            source_file="2021-06.pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].description, "Sample FX Merchant")
        self.assertEqual(rows[0].debited, Decimal("100.00"))


if __name__ == "__main__":
    _ = unittest.main()
