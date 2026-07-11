"""HDFC yearly statement parser tests."""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from networthcsv.pipeline.parse.banks import get_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler

_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _account() -> ResolvedAccount:
    handler = get_handler("hdfc", "default")
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "hdfc",
            "variant": "default",
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class HdfcYearlyParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (_FIXTURES_ROOT / "hdfc/default/yearly-sample.txt").read_text(
            encoding="utf-8"
        )
        cls.account = _account()

    def test_parses_sample_transactions(self) -> None:
        parser = get_parser("hdfc", "default")
        rows = parser.parse(
            self.text,
            account=self.account,
            source_file="yearly-2024-04_2025-03.pdf",
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].description, "SAMPLE MERCHANT ONE")
        self.assertEqual(rows[0].debited, Decimal("100.00"))
        self.assertEqual(rows[1].credited, Decimal("50.00"))


if __name__ == "__main__":
    _ = unittest.main()
