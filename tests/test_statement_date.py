"""Tests for statement date extraction from PDF text."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.pipeline.cleanup.statement_date import (
    extract_statement_date,
    extract_statement_period,
    resolve_month_period,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.statement_period import month_period_from_filename


def _account(
    *,
    bank: str = "bob",
    variant: str | None = None,
) -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
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
        self.assertEqual(parse_date_string("17 Oct 25"), date(2025, 10, 17))

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(parse_date_string("not a date"))


class MonthPeriodFromNameTests(unittest.TestCase):
    def test_yyyy_mm_dd(self) -> None:
        self.assertEqual(
            month_period_from_filename("All Mail__2023-04-18.pdf"), "2023-04"
        )

    def test_yyyy_mm_only(self) -> None:
        self.assertEqual(month_period_from_filename("statement_2024-01.pdf"), "2024-01")

    def test_unknown_when_missing(self) -> None:
        self.assertEqual(month_period_from_filename("attachment.pdf"), "unknown-month")


class ResolveMonthPeriodTests(unittest.TestCase):
    def test_content_wins_over_filename(self) -> None:
        text = (
            "Credit Card Monthly Statement\n"
            "Statement Date : 16/04/2023 | Statement Period : 17 Mar, 2023 to 16 Apr, 2023\n"
        )
        self.assertEqual(
            resolve_month_period(
                text, "All Mail__2023-05-20.pdf", account=_account(bank="bob")
            ),
            "2023-04",
        )

    def test_filename_fallback_when_no_date_in_text(self) -> None:
        text = "bob card ending 5678"
        self.assertEqual(
            resolve_month_period(
                text, "All Mail__2023-04-18.pdf", account=_account(bank="bob")
            ),
            "2023-04",
        )

    def test_unknown_month_when_neither_works(self) -> None:
        text = "no dates here"
        self.assertEqual(
            resolve_month_period(text, "attachment.pdf", account=_account(bank="bob")),
            "unknown-month",
        )


class MultiAttemptTests(unittest.TestCase):
    def test_second_marker_used_when_first_fails(self) -> None:
        account = _account(bank="federal", variant="signet")
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


class ExtractStatementPeriodTests(unittest.TestCase):
    def test_bob_statement_period_range(self) -> None:
        text = (
            "Credit Card Monthly Statement\n"
            "Statement Date : 16/04/2023 | Statement Period : 17 Mar, 2023 to 16 Apr, 2023\n"
        )
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="bob")
        )
        self.assertEqual(period_start, date(2023, 3, 17))
        self.assertEqual(period_end, date(2023, 4, 16))

    def test_indusind_statement_period_bounds(self) -> None:
        text = "Statement Period\n16/01/2024 To 15/02/2024\nStatement Date\n15/02/2024"
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="indusind")
        )
        self.assertEqual(period_start, date(2024, 1, 16))
        self.assertEqual(period_end, date(2024, 2, 15))

    def test_yes_statement_period_bounds(self) -> None:
        text = (
            "Statement Period:          Credit Limit:\n"
            "17/01/2021 To 16/02/2021     Rs. 3,00,000.00\n"
        )
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="yes", variant="ace")
        )
        self.assertEqual(period_start, date(2021, 1, 17))
        self.assertEqual(period_end, date(2021, 2, 16))

    def test_federal_signet_statement_period_bounds(self) -> None:
        text = "Statement Period\n22-03-2021 to 21-04-2021"
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="federal", variant="signet")
        )
        self.assertEqual(period_start, date(2021, 3, 22))
        self.assertEqual(period_end, date(2021, 4, 21))

    def test_fallback_to_statement_date_end_only(self) -> None:
        text = "Statement Date 17/01/2024"
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="idfc", variant="wow")
        )
        self.assertIsNone(period_start)
        self.assertEqual(period_end, date(2024, 1, 17))

    def test_pnb_statement_period_bounds(self) -> None:
        text = (
            "Transaction Date Post Date Trnx Details "
            "From 17-FEB-2024 to 16-MAR-2024 Amount in Rs."
        )
        period_start, period_end = extract_statement_period(
            text, account=_account(bank="pnb", variant="platinum")
        )
        self.assertEqual(period_start, date(2024, 2, 17))
        self.assertEqual(period_end, date(2024, 3, 16))


if __name__ == "__main__":
    _ = unittest.main()
