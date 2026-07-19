"""CSB statement balance extraction tests."""

from __future__ import annotations

import unittest

from helpers import account as make_account
from networthcsv.utils.banks import get_handler


class CsbStatementBalanceTests(unittest.TestCase):
    def test_edge_summary_skips_payment_due_row(self) -> None:
        text = (
            "     Rs. 3,457.05                         01 May  2026\n"
            "     Rs. 500.00                           17/04/2026\n"
            "                     22/03/2026                                         Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
        )
        account = make_account(
            bank="csb",
            variant="edge",
            account_number="1234",
            passwords=["x"],
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        self.assertEqual(opening, "0.00")


if __name__ == "__main__":
    _ = unittest.main()
