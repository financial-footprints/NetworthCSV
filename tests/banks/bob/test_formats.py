"""Tests for BoB format1 and format2 statement layout support using synthetic fixtures."""

from __future__ import annotations

import unittest

from cleanup_support import FIXTURES_ROOT
from networthcsv.utils.banks.period import resolve_month_period
from networthcsv.utils.banks.helpers.text import trim_by_markers
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.base import CreditCardHandler

_FIXTURES = FIXTURES_ROOT / "bob" / "easy"


def _account(*, bank: str = "bob", variant: str | None = "easy") -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": "4829",
            "passwords": ["x"],
            "opening_date": "01-01-2020",
            **defaults.model_dump(),
        }
    )


class BobFormatFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.format2 = (_FIXTURES / "format2.txt").read_text(encoding="utf-8")
        cls.format1 = (_FIXTURES / "format1.txt").read_text(encoding="utf-8")
        cls.account = _account()
        cls.handler = get_handler(cls.account.bank, cls.account.variant)
        assert isinstance(cls.handler, CreditCardHandler)
        end_markers = list(cls.handler.trim_end())
        cls.trimmed_format2 = trim_by_markers(cls.format2, trim_end=end_markers)
        cls.trimmed_format1 = trim_by_markers(cls.format1, trim_end=end_markers)

    def test_format2_month_from_content_not_filename(self) -> None:
        self.assertEqual(
            resolve_month_period(
                self.format2,
                "attachment__2025-08-20.pdf",
                account=self.account,
            ),
            "2025-03",
        )

    def test_format1_month_from_labels(self) -> None:
        self.assertEqual(
            resolve_month_period(
                self.format1,
                "attachment__2025-01-01.pdf",
                account=self.account,
            ),
            "2024-10",
        )

    def test_format2_trim_keeps_page_one_only(self) -> None:
        trimmed = self.trimmed_format2
        self.assertIn("Page 1 of 5", trimmed)
        self.assertNotIn("Page 2 of 5", trimmed)
        self.assertNotIn("SCHEDULE OF CHARGES", trimmed)

    def test_format1_trim_keeps_through_reward_summary(self) -> None:
        trimmed = self.trimmed_format1
        self.assertIn("Reward Summary at Card Level", trimmed)
        self.assertIn("R88002 LIBRARY MEMBERSHIP", trimmed)
        self.assertNotIn("Page 3 of 4", trimmed)

    def test_format2_balances_from_second_summary_row(self) -> None:
        opening = self.handler.get_opening_balance(self.trimmed_format2)
        closing = self.handler.get_closing_balance(self.trimmed_format2)
        self.assertEqual(opening, "-10.00")
        self.assertEqual(closing, "1250.00")

    def test_format1_balances_from_account_summary(self) -> None:
        opening = self.handler.get_opening_balance(self.format1)
        closing = self.handler.get_closing_balance(self.format1)
        self.assertEqual(opening, "42.00")
        self.assertEqual(closing, "192.00")

    def test_clean_text_drops_registration_boilerplate(self) -> None:
        raw = (
            "Tax Invoice to:\n"
            "SAMPLE CARDHOLDER\n"
            "Statement period 17 Jul, 2024 To 16 Aug, 2024\n"
            "18/08/2024 R92485 SAMPLE MERCHANT 200.00 DR\n"
            "via the BOBCARD mobile app or portal for regular alerts.\n"
            "Clickheretoknowmore\n"
            "Page 1 of 5\n"
            "Page 2 of 5\n"
            "SCHEDULE OF CHARGES\n"
            "fee table\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("SAMPLE CARDHOLDER", cleaned)
        self.assertIn("SAMPLE MERCHANT", cleaned)
        self.assertNotIn("via the BOBCARD mobile app or portal", cleaned)
        self.assertNotIn("Clickheretoknowmore", cleaned)
        self.assertNotIn("SCHEDULE OF CHARGES", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
