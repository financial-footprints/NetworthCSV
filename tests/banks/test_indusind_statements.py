"""IndusInd statement balance extraction tests."""

from __future__ import annotations

import unittest

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler


def _account(*, variant: str | None = "default") -> ResolvedAccount:
    handler = get_handler("indusind", variant)
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "indusind",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class IndusindStatementBalanceTests(unittest.TestCase):
    def test_previous_balance_next_line(self) -> None:
        text = "Previous Balance\n0.00 DR\nTotal Amount Due\n990.00 CR\n"
        account = _account()
        handler = get_handler(account.bank, account.variant)
        opening = handler.get_opening_balance(text)
        closing = handler.get_closing_balance(text)
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-990.00")


if __name__ == "__main__":
    _ = unittest.main()
