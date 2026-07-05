"""Tests for statement date extraction from PDF text."""

from __future__ import annotations

import json
import unittest
from datetime import date

from networthcsv.pipeline.cleanup.statement_date import (
    extract_statement_date,
    month_stem_from_name,
    parse_date_string,
    resolve_month_stem,
)
from networthcsv.settings import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ResolvedAccount,
    _resolve_variant_defaults,
)

_APP_CONFIG = AppConfig.from_json(
    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")),
    config_path=DEFAULT_CONFIG_PATH,
)


def _account(
    *,
    bank: str = "bob",
    variant: str | None = "easy",
    statement_date_markers: list[dict[str, object]] | None = None,
) -> ResolvedAccount:
    if statement_date_markers is not None:
        return ResolvedAccount.model_validate(
            {
                "bank": bank,
                "variant": variant,
                "account_number": "1234",
                "passwords": ["x"],
                "mail": {"subjects": ["test"]},
                "metadata": {"statement_date": statement_date_markers},
            }
        )
    bank_variants = _APP_CONFIG.banks[bank]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class ParseDateStringTests(unittest.TestCase):
    def test_common_formats(self) -> None:
        self.assertEqual(parse_date_string("16/04/2023"), date(2023, 4, 16))
        self.assertEqual(parse_date_string("20 Aug, 2025"), date(2025, 8, 20))
        self.assertEqual(parse_date_string("16-MAY-2023"), date(2023, 5, 16))
        self.assertEqual(parse_date_string("October 12, 2025"), date(2025, 10, 12))
        self.assertEqual(parse_date_string("April 14, 2026"), date(2026, 4, 14))
        self.assertEqual(parse_date_string("17/May/2026"), date(2026, 5, 17))

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(parse_date_string("not a date"))


class MonthStemFromNameTests(unittest.TestCase):
    def test_yyyy_mm_dd(self) -> None:
        self.assertEqual(month_stem_from_name("All Mail__2023-04-18.pdf"), "2023-04")

    def test_yyyy_mm_only(self) -> None:
        self.assertEqual(month_stem_from_name("statement_2024-01.pdf"), "2024-01")

    def test_unknown_when_missing(self) -> None:
        self.assertEqual(month_stem_from_name("attachment.pdf"), "unknown-month")


class ResolveMonthStemTests(unittest.TestCase):
    def test_content_wins_over_filename(self) -> None:
        text = (
            "Credit Card Monthly Statement\n"
            "Statement Date : 16/04/2023 | Statement Period : 17 Mar, 2023 to 16 Apr, 2023\n"
        )
        self.assertEqual(
            resolve_month_stem(
                text, "All Mail__2023-05-20.pdf", account=_account(bank="bob")
            ),
            "2023-04",
        )

    def test_filename_fallback_when_no_date_in_text(self) -> None:
        text = "bob card ending 5678"
        self.assertEqual(
            resolve_month_stem(
                text, "All Mail__2023-04-18.pdf", account=_account(bank="bob")
            ),
            "2023-04",
        )

    def test_unknown_month_when_neither_works(self) -> None:
        text = "no dates here"
        self.assertEqual(
            resolve_month_stem(text, "attachment.pdf", account=_account(bank="bob")),
            "unknown-month",
        )


class MultiAttemptTests(unittest.TestCase):
    def test_second_marker_used_when_first_fails(self) -> None:
        account = _account(
            statement_date_markers=[
                {"mode": "label_single", "label": "Missing Label"},
                {
                    "mode": "top_range",
                    "joiner": " - ",
                    "take": "end",
                    "search_chars": 2000,
                },
            ]
        )
        text = "21 DEC 2023 - 20 JAN 2024\n\n21/01/2024"
        parsed = extract_statement_date(text, account=account)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual((parsed.year, parsed.month), (2024, 1))


class ExtractStatementDateTests(unittest.TestCase):
    def test_federal_billing_range_end(self) -> None:
        text = "21 DEC 2023 - 20 JAN 2024\n\n21/01/2024"
        parsed = extract_statement_date(
            text, account=_account(bank="federal", variant="edge")
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual((parsed.year, parsed.month), (2024, 1))

    def test_indusind_statement_period_end(self) -> None:
        text = "Statement Period\n16/01/2024 To 15/02/2024\nStatement Date\n15/02/2024"
        parsed = extract_statement_date(text, account=_account(bank="indusind"))
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual((parsed.year, parsed.month), (2024, 2))

    def test_idfc_wow_range_on_label(self) -> None:
        text = "Statement Date 18/Apr/2026 to 17/May/2026"
        parsed = extract_statement_date(
            text, account=_account(bank="idfc", variant="wow")
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed, date(2026, 5, 17))

    def test_idfc_wow_single_on_label(self) -> None:
        text = "Statement Date 17/01/2024"
        parsed = extract_statement_date(
            text, account=_account(bank="idfc", variant="wow")
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed, date(2024, 1, 17))

    def test_idfc_wow_header_range_fallback(self) -> None:
        text = "18/05/2023 - 17/06/2023\nAccount Number Statement Date\n9000000001"
        parsed = extract_statement_date(
            text, account=_account(bank="idfc", variant="wow")
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed, date(2023, 6, 17))


if __name__ == "__main__":
    _ = unittest.main()
