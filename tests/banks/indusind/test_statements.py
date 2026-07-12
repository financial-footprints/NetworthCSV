"""IndusInd statement balance extraction tests."""

from __future__ import annotations

import unittest

from cleanup_support import FIXTURES_ROOT
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.text import text_not_contains_violated

_ANNUAL_SUMMARY_MARKERS = [
    "ANNUAL SPEND SUMMARY",
    "CARD WISE SUMMARY FOR ACCOUNT OF",
    "MONTH WISE SPENDS ON YOUR ACCOUNT",
]


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


class IndusindMatchingDefaultsTests(unittest.TestCase):
    def test_matching_defaults_reject_annual_spend_summary(self) -> None:
        handler = get_handler("indusind", "auraedge")
        defaults = handler.matching_defaults()
        self.assertEqual(
            defaults.statement.text_not_contains,
            _ANNUAL_SUMMARY_MARKERS,
        )
        summary_text = (FIXTURES_ROOT / "indusind/annual-spend-summary.txt").read_text(
            encoding="utf-8"
        )
        sanitized = handler.clean_text(summary_text)
        self.assertTrue(
            text_not_contains_violated(
                sanitized,
                defaults.statement.text_not_contains,
            )
        )

    def test_matching_defaults_allow_real_statement(self) -> None:
        handler = get_handler("indusind", "auraedge")
        defaults = handler.matching_defaults()
        statement_text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        sanitized = handler.clean_text(statement_text)
        self.assertFalse(
            text_not_contains_violated(
                sanitized,
                defaults.statement.text_not_contains,
            )
        )


if __name__ == "__main__":
    _ = unittest.main()
