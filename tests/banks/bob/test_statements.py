"""BoB statement balance extraction tests."""

from __future__ import annotations

import unittest

from cleanup_support import account as make_account
from networthcsv.utils.banks import get_handler


class BobStatementBalanceTests(unittest.TestCase):
    def test_account_summary_table(self) -> None:
        text = (
            "Account Summary\n"
            "                                (cid:28)                  / (cid:20)          N   e    w /          (cid:34)\n"
            "Opening Balance Payment/Credits        Closing Balance\n"
            "                               Purchases/Debits\n"
            "    .00        1,001.00      10.00        -991.00\n"
            "Bonus/Reward Points Summary\n"
            "Opening Balance Earned    Redeemed/Expired Closing Balance\n"
            "    0             0            0            0\n"
        )
        account = make_account(
            bank="bob",
            variant="easy",
            account_number="1234",
            passwords=["x"],
        )
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-991.00")


if __name__ == "__main__":
    _ = unittest.main()
