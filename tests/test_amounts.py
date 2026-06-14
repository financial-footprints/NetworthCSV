"""Amount and transaction helper tests."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from src.core.amounts import dedupe_transactions, make_transaction, parse_amount
from src.core.transactions import Transaction


class AmountTests(unittest.TestCase):
    def test_parse_amount_debit(self) -> None:
        credited, debited = parse_amount("1,234.56", is_credit=False)
        self.assertEqual(credited, Decimal(0))
        self.assertEqual(debited, Decimal("1234.56"))

    def test_parse_amount_credit(self) -> None:
        credited, debited = parse_amount("500.00", is_credit=True)
        self.assertEqual(credited, Decimal("500.00"))
        self.assertEqual(debited, Decimal(0))

    def test_make_transaction(self) -> None:
        txn = make_transaction(
            date(2024, 1, 15),
            "STORE",
            "100.00",
            False,
            "2024-01.pdf",
            ref_no="R1",
        )
        self.assertEqual(txn.debited, Decimal("100.00"))
        self.assertEqual(txn.ref_no, "R1")

    def test_dedupe_transactions(self) -> None:
        first = Transaction(
            date=date(2024, 1, 1),
            description="A",
            credited=Decimal(0),
            debited=Decimal("1.00"),
            source_file="a.pdf",
        )
        duplicate = Transaction(
            date=date(2024, 1, 1),
            description="A",
            credited=Decimal(0),
            debited=Decimal("1.00"),
            source_file="a.pdf",
        )
        different = Transaction(
            date=date(2024, 1, 2),
            description="B",
            credited=Decimal(0),
            debited=Decimal("2.00"),
            source_file="a.pdf",
        )
        result = dedupe_transactions([first, duplicate, different])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
