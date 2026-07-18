"""YES Bank transaction parser tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from cleanup_support import account as make_account
from networthcsv.pipeline.parse.banks import get_parser


class YesParserTests(unittest.TestCase):
    def test_parses_bbps_credit_line(self) -> None:
        text = (
            "Statement Details\n"
            "Date  Transaction Details                    Merchant Category Amount (Rs.)\n"
            "17/03/2021 PAYMENT RECEIVED BBPS - Ref No: 09999999980317000950039 2,065.08 Cr\n"
        )
        account = make_account(bank="yes", variant="ace")
        rows = get_parser("yes", "ace").parse(
            text, account=account, source_file="2021-03.pdf"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].credited, Decimal("2065.08"))


if __name__ == "__main__":
    _ = unittest.main()
