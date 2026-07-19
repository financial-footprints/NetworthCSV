"""Account metadata generation tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from helpers import account as make_account
from helpers import run_context
from networthcsv.pipeline.metadata import (
    BalanceGap,
    StatementMetadata,
    build_account_metadata,
    build_period_covered,
    build_annual_statement_summaries,
    compute_balance_gaps,
    covered_month,
    load_account_metadata,
    months_between_exclusive,
    read_account_metadata,
    read_last_fetch_date,
    refresh_account_metadata,
    run_account,
    statement_date_for_covered_month,
    write_last_fetch_date,
)
from networthcsv.pipeline.metadata.persist import write_account_metadata
from networthcsv.settings import (
    ResolvedAccount,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.path import (
    account_fy_dir,
    account_metadata_path,
    fy_folder_name,
    statement_csv_path,
)


def _write_statement(
    download_path: Path,
    account: ResolvedAccount,
    statement_period: str,
    *,
    with_txt: bool = True,
) -> None:
    fy_dir = account_fy_dir(download_path, account, fy_folder_name(statement_period))
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fy_dir / f"{statement_period}.pdf"
    _ = pdf_path.write_bytes(b"%PDF-1.4")
    if with_txt:
        _ = (fy_dir / f"{statement_period}.txt").write_text(
            "statement", encoding="utf-8"
        )


class CoveredMonthTests(unittest.TestCase):
    def test_subtracts_one_month(self) -> None:
        self.assertEqual(covered_month("2025-04"), "2025-03")

    def test_january_rolls_to_previous_december(self) -> None:
        self.assertEqual(covered_month("2025-01"), "2024-12")

    def test_statement_date_for_covered_month_inverts(self) -> None:
        self.assertEqual(statement_date_for_covered_month("2025-03"), "2025-04")
        self.assertEqual(statement_date_for_covered_month("2024-12"), "2025-01")

    def test_round_trip_month_conversion(self) -> None:
        for statement_date in ("2024-01", "2024-06", "2025-01"):
            covered = covered_month(statement_date)
            self.assertEqual(
                statement_date_for_covered_month(covered),
                statement_date,
            )


class MonthsBetweenExclusiveTests(unittest.TestCase):
    def test_adjacent_months_returns_empty(self) -> None:
        self.assertEqual(months_between_exclusive("2024-01", "2024-02"), ())

    def test_single_gap_month(self) -> None:
        self.assertEqual(months_between_exclusive("2024-01", "2024-03"), ("2024-02",))

    def test_multiple_gap_months(self) -> None:
        self.assertEqual(
            months_between_exclusive("2024-01", "2024-04"),
            ("2024-02", "2024-03"),
        )

    def test_reversed_or_equal_returns_empty(self) -> None:
        self.assertEqual(months_between_exclusive("2024-03", "2024-01"), ())
        self.assertEqual(months_between_exclusive("2024-03", "2024-03"), ())

    def test_month_cursor_advances_across_year_boundary(self) -> None:
        self.assertEqual(
            months_between_exclusive("2024-11", "2025-02"),
            ("2024-12", "2025-01"),
        )


class ComputeBalanceGapsTests(unittest.TestCase):
    def test_adjacent_statements_produce_no_gaps(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance="10.00",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_adjacent_statements_mismatch_marks_discontinuity(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance="15.00",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(
            compute_balance_gaps(statements),
            (
                BalanceGap(month="2024-01", status="discontinuity"),
                BalanceGap(month="2024-02", status="discontinuity"),
            ),
        )

    def test_adjacent_statements_missing_balance_skips_discontinuity(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance=None,
                closing_balance="20.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_matching_balances_across_gap(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-04",
                formats=("pdf",),
                opening_balance="10.00",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(
            compute_balance_gaps(statements),
            (BalanceGap(month="2024-02", status="matched"),),
        )

    def test_mismatched_balances_across_gap(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                opening_balance="15.00",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(
            compute_balance_gaps(statements),
            (
                BalanceGap(month="2024-02", status="mismatched"),
                BalanceGap(month="2024-03", status="mismatched"),
            ),
        )

    def test_missing_balance_skips_gap(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance=None,
            ),
            StatementMetadata(
                statement_date="2024-04",
                formats=("pdf",),
                opening_balance="10.00",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_adjacent_statements_small_diff_produces_no_gaps(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="11000.00",
                closing_balance="11111.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance="11111.01",
                closing_balance="11500.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_adjacent_statements_diff_above_tolerance_marks_discontinuity(
        self,
    ) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="11000.00",
                closing_balance="11111.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance="11111.22",
                closing_balance="11500.00",
            ),
        )

        self.assertEqual(
            compute_balance_gaps(statements),
            (
                BalanceGap(month="2024-01", status="discontinuity"),
                BalanceGap(month="2024-02", status="discontinuity"),
            ),
        )

    def test_adjacent_statements_boundary_tolerance_produces_no_gaps(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="11000.00",
                closing_balance="11111.00",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                opening_balance="11111.21",
                closing_balance="11500.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_small_diff_across_gap_is_matched(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
            StatementMetadata(
                statement_date="2024-04",
                formats=("pdf",),
                opening_balance="10.01",
                closing_balance="20.00",
            ),
        )

        self.assertEqual(
            compute_balance_gaps(statements),
            (BalanceGap(month="2024-02", status="matched"),),
        )

    def test_adjacent_credit_card_statements_no_discontinuity(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2021-05",
                formats=("pdf",),
                opening_balance="-2222.22",
                closing_balance="11111.11",
            ),
            StatementMetadata(
                statement_date="2021-06",
                formats=("pdf",),
                opening_balance="11111.11",
                closing_balance="-555.55",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())

    def test_single_statement_produces_no_gaps(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                opening_balance="0.00",
                closing_balance="10.00",
            ),
        )

        self.assertEqual(compute_balance_gaps(statements), ())


class BuildPeriodCoveredTests(unittest.TestCase):
    def test_touching_periods_merge_into_one_segment(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="16-04-2024",
                period_end="16-05-2024",
            ),
            StatementMetadata(
                statement_date="2024-06",
                formats=("pdf",),
                period_start="16-05-2024",
                period_end="16-06-2024",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.segments), 1)
        self.assertEqual(period.segments[0].start, "16-04-2024")
        self.assertEqual(period.segments[0].end, "16-06-2024")
        self.assertEqual(period.gaps, ())
        self.assertEqual(period.start, "16-04-2024")
        self.assertEqual(period.end, "16-06-2024")

    def test_consecutive_billing_cycles_merge(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-01",
                formats=("pdf",),
                period_start="21-12-2023",
                period_end="20-01-2024",
            ),
            StatementMetadata(
                statement_date="2024-02",
                formats=("pdf",),
                period_start="21-01-2024",
                period_end="20-02-2024",
            ),
            StatementMetadata(
                statement_date="2024-03",
                formats=("pdf",),
                period_start="21-02-2024",
                period_end="20-03-2024",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.segments), 1)
        self.assertEqual(period.segments[0].start, "21-12-2023")
        self.assertEqual(period.segments[0].end, "20-03-2024")
        self.assertEqual(period.gaps, ())

    def test_non_adjacent_periods_create_gap(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="16-04-2024",
                period_end="16-05-2024",
            ),
            StatementMetadata(
                statement_date="2024-07",
                formats=("pdf",),
                period_start="16-06-2024",
                period_end="16-07-2024",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.segments), 2)
        self.assertEqual(len(period.gaps), 1)
        self.assertEqual(period.gaps[0].start, "17-05-2024")
        self.assertEqual(period.gaps[0].end, "15-06-2024")
        self.assertIsNone(period.gaps[0].balances_match)

    def test_period_gap_balances_match_when_amounts_align(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-01",
                formats=("pdf",),
                period_start="21-12-2023",
                period_end="20-01-2024",
                closing_balance="1250.00",
            ),
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="21-04-2024",
                period_end="20-05-2024",
                opening_balance="1250.00",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.gaps), 1)
        self.assertEqual(period.gaps[0].start, "21-01-2024")
        self.assertEqual(period.gaps[0].end, "20-04-2024")
        self.assertTrue(period.gaps[0].balances_match)

    def test_period_gap_balances_mismatch_when_amounts_differ(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-01",
                formats=("pdf",),
                period_start="21-12-2023",
                period_end="20-01-2024",
                closing_balance="1250.00",
            ),
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="21-04-2024",
                period_end="20-05-2024",
                opening_balance="1500.00",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.gaps), 1)
        self.assertFalse(period.gaps[0].balances_match)

    def test_period_gap_balances_unknown_when_balances_missing(self) -> None:
        statements = (
            StatementMetadata(
                statement_date="2024-01",
                formats=("pdf",),
                period_start="21-12-2023",
                period_end="20-01-2024",
            ),
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="21-04-2024",
                period_end="20-05-2024",
                opening_balance="1500.00",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.gaps), 1)
        self.assertIsNone(period.gaps[0].balances_match)

    def test_period_gap_balances_ignore_annual_opening(self) -> None:
        """Annual can bound the gap dates but must not drive balances_match."""
        statements = (
            StatementMetadata(
                statement_date="2024-01",
                formats=("pdf",),
                period_start="21-12-2023",
                period_end="20-01-2024",
                closing_balance="-3047.00",
            ),
            StatementMetadata(
                statement_date="FY24-2025",
                formats=("pdf",),
                period_start="01-04-2024",
                period_end="31-03-2025",
                opening_balance="21850.02",
                closing_balance="800000.00",
                granularity="annual",
                covered_months=(
                    "2024-04",
                    "2024-05",
                    "2024-06",
                    "2024-07",
                    "2024-08",
                    "2024-09",
                    "2024-10",
                    "2024-11",
                    "2024-12",
                    "2025-01",
                    "2025-02",
                    "2025-03",
                ),
                year_key="FY24-2025",
            ),
            StatementMetadata(
                statement_date="2024-05",
                formats=("pdf",),
                period_start="21-04-2024",
                period_end="20-05-2024",
                opening_balance="-3047.00",
            ),
        )

        period = build_period_covered(statements)

        self.assertEqual(len(period.gaps), 1)
        self.assertEqual(period.gaps[0].start, "21-01-2024")
        self.assertEqual(period.gaps[0].end, "31-03-2024")
        self.assertTrue(period.gaps[0].balances_match)

    def test_statements_without_periods_keep_months_only(self) -> None:
        statements = (
            StatementMetadata(statement_date="2024-01", formats=("pdf",)),
            StatementMetadata(statement_date="2024-02", formats=("pdf",)),
        )

        period = build_period_covered(statements)

        self.assertEqual(period.segments, ())
        self.assertEqual(period.gaps, ())
        self.assertIsNone(period.start)
        self.assertIsNone(period.end)
        self.assertEqual(period.months, ("2023-12", "2024-01"))


class ReadAccountMetadataTests(unittest.TestCase):
    def test_read_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            _write_statement(download_path, account, "2024-01")

            written = build_account_metadata(download_path, account)
            path = account_metadata_path(download_path, account)
            refresh_account_metadata(download_path, account)

            loaded = read_account_metadata(path)
            assert loaded is not None
            self.assertEqual(loaded.statement_count, written.statement_count)
            self.assertEqual(loaded.statement_dates, written.statement_dates)
            self.assertEqual(
                loaded.period_covered.months, written.period_covered.months
            )

    def test_read_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            self.assertIsNone(read_account_metadata(path))

    def test_load_falls_back_to_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            _write_statement(download_path, account, "2024-02")

            metadata, from_file = load_account_metadata(download_path, account)

            self.assertFalse(from_file)
            self.assertEqual(metadata.statement_count, 1)
            self.assertEqual(metadata.statement_dates, ("2024-02",))

    def test_load_reads_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            _write_statement(download_path, account, "2024-03")
            refresh_account_metadata(download_path, account)

            metadata, from_file = load_account_metadata(download_path, account)

            self.assertTrue(from_file)
            self.assertEqual(metadata.statement_count, 1)


class BuildAccountMetadataTests(unittest.TestCase):
    def test_builds_from_statement_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            _write_statement(download_path, account, "2024-01")
            _write_statement(download_path, account, "2024-02")

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.statement_count, 2)
            self.assertEqual(metadata.statement_dates, ("2024-01", "2024-02"))
            self.assertEqual(metadata.starting, "2024-01")
            self.assertEqual(metadata.ending, "2024-02")
            self.assertEqual(metadata.formats, ("pdf", "txt"))
            self.assertEqual(
                metadata.statements[0].formats,
                ("pdf", "txt"),
            )

    def test_extracts_balances_when_statement_text_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text(
                "Account Summary\n"
                "                                (cid:28)                  / (cid:20)          N   e    w /          (cid:34)\n"
                "Opening Balance Payment/Credits        Closing Balance\n"
                "                               Purchases/Debits\n"
                "    .00        1,001.00      10.00        -991.00\n"
                "Bonus/Reward Points Summary\n"
                "Opening Balance Earned    Redeemed/Expired Closing Balance\n"
                "    0             0            0            0\n",
                encoding="utf-8",
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.statements[0].opening_balance, "0.00")
            self.assertEqual(metadata.statements[0].closing_balance, "-991.00")

    def test_opening_date_does_not_filter_period_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(opening_date=date(2023, 4, 1))
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            for month in ("2023-04", "2023-05"):
                _ = (fy_dir / f"{month}.pdf").write_bytes(b"%PDF")
                _ = (fy_dir / f"{month}.txt").write_text("x", encoding="utf-8")

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.period_covered.months, ("2023-03", "2023-04"))

    def test_opening_date_does_not_truncate_early_statements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(opening_date=date(2023, 6, 1))
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            for month in ("2023-04", "2023-05", "2023-06", "2023-07"):
                _ = (fy_dir / f"{month}.pdf").write_bytes(b"%PDF")
                _ = (fy_dir / f"{month}.txt").write_text("x", encoding="utf-8")

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(
                metadata.period_covered.months,
                ("2023-03", "2023-04", "2023-05", "2023-06"),
            )
            self.assertEqual(metadata.period_covered.segments, ())

    def test_closing_date_exported_without_filtering_period_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(
                opening_date=date(2023, 4, 1),
                closing_date=date(2024, 8, 1),
            )
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            for month in ("2023-04", "2023-05"):
                _ = (fy_dir / f"{month}.pdf").write_bytes(b"%PDF")
                _ = (fy_dir / f"{month}.txt").write_text("x", encoding="utf-8")

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.opening_date, "01-04-2023")
            self.assertEqual(metadata.closing_date, "01-08-2024")
            self.assertEqual(metadata.period_covered.months, ("2023-03", "2023-04"))

    def test_csv_detected_in_fy_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")
            _ = (fy_dir / "transactions-2024-01.csv").write_text(
                "Date,Description\n", encoding="utf-8"
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.formats, ("csv", "pdf", "txt"))

    def test_builds_day_level_period_from_statement_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-10.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-10.txt").write_text(
                "Statement Date : 16/10/2024 | Statement Period : 17 Sep, 2024 to 16 Oct, 2024\n",
                encoding="utf-8",
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.statements[0].period_start, "17-09-2024")
            self.assertEqual(metadata.statements[0].period_end, "16-10-2024")
            self.assertFalse(metadata.statements[0].period_approximate)
            self.assertEqual(len(metadata.period_covered.segments), 1)
            self.assertEqual(metadata.period_covered.segments[0].start, "17-09-2024")
            self.assertEqual(metadata.period_covered.segments[0].end, "16-10-2024")

    def test_hdfc_derives_period_from_previous_month_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="hdfc", variant="regalia")
            fy_dir = account_fy_dir(download_path, account, "FY21-2022")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2021-09.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2021-09.txt").write_text(
                "Statement Date:20/09/2021\n",
                encoding="utf-8",
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.statements[0].period_start, "21-08-2021")
            self.assertEqual(metadata.statements[0].period_end, "20-09-2021")
            self.assertTrue(metadata.statements[0].period_approximate)

    def test_extracted_period_range_wins_over_statement_period_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account(bank="hdfc", variant="regalia")
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-10.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-10.txt").write_text(
                "Statement Date : 16/10/2024 | Billing Period : 17 Sep, 2024 - 16 Oct, 2024\n",
                encoding="utf-8",
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.statements[0].period_start, "17-09-2024")
            self.assertEqual(metadata.statements[0].period_end, "16-10-2024")


class AnnualCsvYearKeyMetadataTests(unittest.TestCase):
    _ICICI_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "icici" / "csv"

    def test_four_icici_annual_csvs_map_to_four_fy_chips(self) -> None:
        account = make_account(
            bank="icici",
            variant="default",
            account_number="7788",
            opening_date=date(2023, 5, 17),
        )
        periods = [
            "FY22-2023",
            "FY23-2024",
            "FY24-2025",
            "FY25-2026",
        ]
        fy22_text = (self._ICICI_FIXTURES / "annual-fy22-sample.csv").read_text(
            encoding="utf-8",
        )
        fy24_text = (self._ICICI_FIXTURES / "annual-sample.csv").read_text(
            encoding="utf-8",
        )
        contents = [fy22_text, fy22_text, fy24_text, fy24_text]

        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            for period, text in zip(periods, contents, strict=True):
                target = statement_csv_path(download_path, account, period)
                _ = target.parent.mkdir(parents=True, exist_ok=True)
                _ = target.write_text(text, encoding="utf-8")

            metadata = build_account_metadata(download_path, account)
            handler = get_handler("icici", "default")
            summaries = build_annual_statement_summaries(
                metadata.statements,
                year_display=handler.year_display(),
            )
            self.assertEqual(len(summaries), 4)
            year_keys = {item.year_key for item in summaries}
            self.assertEqual(
                year_keys,
                {"FY22-2023", "FY23-2024", "FY24-2025", "FY25-2026"},
            )
            for summary in summaries:
                self.assertIn("csv", summary.formats)

    def test_fy25_annual_csv_lands_in_fy25_folder(self) -> None:
        account = make_account(
            bank="icici",
            variant="default",
            account_number="6005",
            opening_date=date(2023, 5, 17),
        )
        text = (self._ICICI_FIXTURES / "annual-fy25-sample.csv").read_text(
            encoding="utf-8",
        )
        period = "FY25-2026"

        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            target = statement_csv_path(download_path, account, period)
            self.assertIn("FY25-2026", target.as_posix())
            self.assertTrue(target.name.endswith("2026.csv"))
            _ = target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text(text, encoding="utf-8")

            metadata = build_account_metadata(download_path, account)
            handler = get_handler("icici", "default")
            summaries = build_annual_statement_summaries(
                metadata.statements,
                year_display=handler.year_display(),
            )
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].year_key, "FY25-2026")
            self.assertIn("csv", summaries[0].formats)


class RefreshAccountMetadataTests(unittest.TestCase):
    def test_writes_metadata_json_to_staging_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")

            path = refresh_account_metadata(download_path, account)

            expected = account_metadata_path(download_path, account)
            self.assertEqual(path, expected)
            self.assertTrue(expected.is_file())
            payload = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(payload["statement_count"], 1)
            self.assertEqual(payload["statement_dates"], ["2024-01"])
            self.assertIn("opening_balance", payload["statements"][0])
            self.assertIn("closing_balance", payload["statements"][0])
            self.assertEqual(payload["period_covered"]["months"], ["2023-12"])
            self.assertIn("segments", payload["period_covered"])
            self.assertIn("gaps", payload["period_covered"])

    def test_refresh_preserves_last_fetch_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")
            _ = write_last_fetch_date(download_path, account, date(2026, 1, 20))

            path = refresh_account_metadata(download_path, account)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["last_fetch_date"], "20-01-2026")
            self.assertEqual(payload["statement_count"], 1)


class LastFetchDateTests(unittest.TestCase):
    def test_write_creates_minimal_metadata_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()

            path = write_last_fetch_date(download_path, account, date(2026, 1, 20))

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["last_fetch_date"], "20-01-2026")

    def test_write_patches_existing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            metadata_path = account_metadata_path(download_path, account)
            _ = metadata_path.parent.mkdir(parents=True, exist_ok=True)
            _ = metadata_path.write_text(
                json.dumps({"statement_count": 2}) + "\n",
                encoding="utf-8",
            )

            _ = write_last_fetch_date(download_path, account, date(2026, 1, 21))

            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["last_fetch_date"], "21-01-2026")
            self.assertEqual(payload["statement_count"], 2)

    def test_read_last_fetch_date_from_partial_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            metadata_path = account_metadata_path(download_path, account)
            _ = metadata_path.parent.mkdir(parents=True, exist_ok=True)
            _ = metadata_path.write_text(
                '{"last_fetch_date": "19-01-2026"}\n',
                encoding="utf-8",
            )

            self.assertEqual(
                read_last_fetch_date(download_path, account),
                date(2026, 1, 19),
            )

    def test_round_trip_last_fetch_date_in_full_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            _write_statement(download_path, account, "2024-01")
            metadata = replace(
                build_account_metadata(download_path, account),
                last_fetch_date="20-01-2026",
            )
            path = account_metadata_path(download_path, account)
            write_account_metadata(path, metadata)

            loaded = read_account_metadata(path)
            assert loaded is not None
            self.assertEqual(loaded.last_fetch_date, "20-01-2026")


class RunAccountMetadataTests(unittest.TestCase):
    def test_run_account_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")

            ctx = run_context(download_path)
            result = run_account(ctx, account)

            metadata_path = account_metadata_path(download_path, account)
            self.assertEqual(result.output, metadata_path)
            self.assertEqual(result.statement_count, 1)
            self.assertTrue(metadata_path.is_file())
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["statement_count"], 1)

    def test_run_account_preserves_last_fetch_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = make_account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")
            _ = write_last_fetch_date(download_path, account, date(2026, 1, 20))

            ctx = run_context(download_path)
            _ = run_account(ctx, account)

            metadata_path = account_metadata_path(download_path, account)
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["last_fetch_date"], "20-01-2026")
