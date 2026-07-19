"""ICICI CSV period classification tests."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from helpers import account as make_account
from pydantic import ValidationError

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks.icici.csv import (
    parse_icici_csv_rows,
    resolve_icici_csv_period_bounds,
    resolve_icici_csv_period_key_with_source,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "icici" / "csv"


def _csv_with_txns(rows: list[tuple[str, str]]) -> str:
    lines = [
        '"Accountno:","0000000099123456"',
        '"Customer Name:","MS. SAMPLE USER BETA"',
        '"Address:","44 TEST AVENUE, SAMPLE TOWN ST 560001"',
        "",
        '"Transaction Details:"',
        '"Date","Sr.No.","Transaction Details","Reward Point Header",'
        '"Intl.Amount","Amount(in Rs)","BillingAmountSign"',
        '"5123 XXXX XXXX 7788"',
    ]
    for index, (txn_date, amount) in enumerate(rows, start=1):
        lines.append(
            f'"{txn_date}","{index}","SAMPLE MERCHANT","10","0.00","{amount}","'
            f'{amount}"'
        )
    lines.extend(
        [
            "",
            '"MESSAGE Details:"',
            '"SRNO,LAST_UPD_DT,MESSAGE"',
            '"1","2018-07-05 00:00:00.0","Safe Banking Tips - sample message only."',
        ]
    )
    return "\n".join(lines)


def _csv_with_inline_statement_period(
    period_line: str,
    rows: list[tuple[str, str]],
) -> str:
    lines = _csv_with_txns(rows).split("\n")
    lines.insert(4, period_line)
    return "\n".join(lines)


class IciciCsvPeriodTests(unittest.TestCase):
    def test_monthly_sample_single_billing_period(self) -> None:
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        # Anchor day 1 → April 2026 is one calendar month.
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "INBOX__2026-04-10.csv", account=account
        )
        self.assertEqual(period, "2026-04")
        self.assertEqual(source, "content_date")

    def test_annual_sample_spans_multiple_billing_periods(self) -> None:
        text = (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "INBOX__2024-05-20.csv", account=account
        )
        self.assertEqual(period, "FY24-2025")
        self.assertEqual(source, "annual")

    def test_annual_filename_forces_annual_when_txns_are_monthly(self) -> None:
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "INBOX__2026-04-10__annual.csv", account=account
        )
        self.assertEqual(period, "FY26-2027")
        self.assertEqual(source, "annual")

    def test_content_statement_period_monthly(self) -> None:
        base = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        text = f'"Statement period :","01-APR-2026 to 30-APR-2026"\n{base}'
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "opaque-name.csv", account=account
        )
        self.assertEqual(period, "2026-04")
        self.assertEqual(source, "content_date")

    def test_inline_statement_period_monthly(self) -> None:
        text = _csv_with_inline_statement_period(
            "Statement Period: 01/04/2026 to 30/04/2026,",
            [("02/04/2026", "200.00")],
        )
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "opaque-name.csv", account=account
        )
        self.assertEqual(period, "2026-04")
        self.assertEqual(source, "content_date")

        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, date(2026, 4, 30))

    def test_inline_statement_period_annual(self) -> None:
        text = _csv_with_inline_statement_period(
            "Statement Period: 01/04/2025 to 31/03/2026,",
            [("14-APR-25", "1,599.00")],
        )
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "opaque-name.csv", account=account
        )
        self.assertEqual(period, "FY25-2026")
        self.assertEqual(source, "annual")

        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2025, 4, 1))
        self.assertEqual(end, date(2026, 3, 31))

    def test_txn_period_with_opening_date(self) -> None:
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "INBOX__2026-04-10.csv", account=account
        )
        self.assertEqual(period, "2026-04")
        self.assertEqual(source, "content_date")

    def test_period_bounds_from_monthly(self) -> None:
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, date(2026, 4, 30))

    def test_period_bounds_from_annual_sample(self) -> None:
        text = (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2024, 4, 1))
        self.assertEqual(end, date(2025, 3, 31))

    def test_period_bounds_from_annual_fy22_sample(self) -> None:
        text = (FIXTURES / "annual-fy22-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2022, 4, 1))
        self.assertEqual(end, date(2023, 3, 31))

    def test_period_bounds_from_annual_fy25_sample(self) -> None:
        text = (FIXTURES / "annual-fy25-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2025, 4, 1))
        self.assertEqual(end, date(2026, 3, 31))

    def test_period_bounds_from_content_statement_period(self) -> None:
        base = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        text = f'"Statement period :","01-APR-2026 to 30-APR-2026"\n{base}'
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2020, 1, 1),
        )
        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, date(2026, 4, 30))

    def test_annual_span_maps_to_fiscal_year(self) -> None:
        text = (
            '"Accountno:","0000000099123456"\n'
            '"Customer Name:","MS. SAMPLE USER BETA"\n'
            '"Address:","44 TEST AVENUE, SAMPLE TOWN ST 560001"\n\n'
            '"Transaction Details:"\n'
            '"Date","Sr.No.","Transaction Details","Reward Point Header",'
            '"Intl.Amount","Amount(in Rs)","BillingAmountSign"\n'
            '"5123 XXXX XXXX 7788"\n'
            '"11-APR-23","1","SAMPLE MERCHANT BANGALORE IN","10","0.00","500.00","500.00"\n'
            '"09-FEB-24","76","SAMPLE MARKETPLACE HTTP EXAMPLE IN","17","0.00","349.00","349.00"\n\n'
            '"MESSAGE Details:"\n'
            '"SRNO,LAST_UPD_DT,MESSAGE"\n'
            '"1","2018-07-05 00:00:00.0","Safe Banking Tips - sample message only."\n'
        )
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text,
            "export.csv",
            account=account,
        )
        self.assertEqual(period, "FY23-2024")
        self.assertEqual(source, "annual")

        start, end = resolve_icici_csv_period_bounds(text, account=account)
        self.assertEqual(start, date(2023, 4, 1))
        self.assertEqual(end, date(2024, 3, 31))

    def test_anchor_day_17_mar_and_apr_same_cycle_is_monthly(self) -> None:
        text = _csv_with_txns([("25-MAR-26", "100.00"), ("05-APR-26", "200.00")])
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "export.csv", account=account
        )
        self.assertEqual(period, "2026-04")
        self.assertEqual(source, "content_date")

    def test_anchor_day_17_apr_and_may_distinct_cycles_is_annual(self) -> None:
        text = _csv_with_txns([("20-APR-26", "100.00"), ("20-MAY-26", "200.00")])
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text, "export.csv", account=account
        )
        self.assertEqual(period, "FY26-2027")
        self.assertEqual(source, "annual")

    def test_parse_rows_both_date_formats(self) -> None:
        annual = parse_icici_csv_rows(
            (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        )
        monthly = parse_icici_csv_rows(
            (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        )
        self.assertEqual(len(annual), 9)
        self.assertEqual(annual[0].date, date(2024, 4, 11))
        self.assertEqual(len(monthly), 3)
        self.assertEqual(monthly[0].date, date(2026, 4, 2))

    def test_annual_fy25_sample_maps_to_fy25_year_key(self) -> None:
        text = (FIXTURES / "annual-fy25-sample.csv").read_text(encoding="utf-8")
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        period, source = resolve_icici_csv_period_key_with_source(
            text,
            "export.csv",
            account=account,
        )
        self.assertEqual(period, "FY25-2026")
        self.assertEqual(source, "annual")

    def test_missing_opening_date_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = ResolvedAccount.model_validate(
                {
                    "bank": "icici",
                    "variant": "default",
                    "account_number": "7788",
                    "passwords": ["secret"],
                    "mail": {
                        "subjects": ["ICICI Bank Credit Card Statement for the period"],
                        "body_contains": [],
                        "from": [],
                    },
                    "statement": {"text_contains": []},
                }
            )


if __name__ == "__main__":
    _ = unittest.main()
