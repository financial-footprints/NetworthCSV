"""Tests for BoB format1 and format2 statement layout support using synthetic fixtures."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from networthcsv.pipeline.cleanup.statement_date import resolve_month_stem
from networthcsv.pipeline.cleanup.statement_text import trim_by_markers
from networthcsv.pipeline.metadata.statement_balance import (
    extract_closing_balance,
    extract_opening_balance,
)
from networthcsv.settings import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ResolvedAccount,
    _resolve_variant_defaults,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bob" / "easy"
_APP_CONFIG = AppConfig.from_json(
    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")),
    config_path=DEFAULT_CONFIG_PATH,
)


def _account(*, bank: str = "bob", variant: str | None = "easy") -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks[bank]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": "4829",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class BobFormatFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.format2 = (_FIXTURES / "format2.txt").read_text(encoding="utf-8")
        cls.format1 = (_FIXTURES / "format1.txt").read_text(encoding="utf-8")
        cls.account = _account()
        end_markers = list(cls.account.statement.trim_end)
        cls.trimmed_format2 = trim_by_markers(cls.format2, trim_end=end_markers)
        cls.trimmed_format1 = trim_by_markers(cls.format1, trim_end=end_markers)

    def test_format2_month_from_content_not_filename(self) -> None:
        self.assertEqual(
            resolve_month_stem(
                self.format2,
                "attachment__2025-08-20.pdf",
                account=self.account,
            ),
            "2025-03",
        )

    def test_format1_month_from_labels(self) -> None:
        self.assertEqual(
            resolve_month_stem(
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
        opening = extract_opening_balance(
            self.trimmed_format2,
            tuple(self.account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            self.trimmed_format2,
            tuple(self.account.metadata.balances.closing),
        )
        self.assertEqual(opening, "-10.00")
        self.assertEqual(closing, "1250.00")

    def test_format1_balances_from_account_summary(self) -> None:
        opening = extract_opening_balance(
            self.format1,
            tuple(self.account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            self.format1,
            tuple(self.account.metadata.balances.closing),
        )
        self.assertEqual(opening, "42.00")
        self.assertEqual(closing, "192.00")


if __name__ == "__main__":
    _ = unittest.main()
