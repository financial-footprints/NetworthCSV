"""CSB statement balance extraction tests."""

from __future__ import annotations

import unittest

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler


def _account(*, variant: str | None = "edge") -> ResolvedAccount:
    handler = get_handler("csb", variant)
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "csb",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            "opening_date": "01-01-2020",
            **defaults.model_dump(),
        }
    )


class CsbStatementBalanceTests(unittest.TestCase):
    def test_edge_summary_skips_payment_due_row(self) -> None:
        text = (
            "     Rs. 3,457.05                         01 May  2026\n"
            "     Rs. 500.00                           17/04/2026\n"
            "                     22/03/2026                                         Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
        )
        account = _account()
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        self.assertEqual(opening, "0.00")


if __name__ == "__main__":
    _ = unittest.main()
