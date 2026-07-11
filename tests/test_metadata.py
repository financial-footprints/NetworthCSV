"""Account metadata generation tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.metadata.metadata import (
    BalanceGap,
    build_account_metadata,
    compute_balance_gaps,
    covered_month,
    load_account_metadata,
    months_between_exclusive,
    read_account_metadata,
    refresh_account_metadata,
    run_account,
    statement_date_for_covered_month,
    StatementMetadata,
    _build_period_covered,
)
from networthcsv.pipeline.reporter import NullRunReporter
from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.path import (
    account_fy_dir,
    account_metadata_path,
    fy_folder_name,
)


def _account(
    *,
    account_number: str = "5678",
    opening_date: date | None = None,
    closing_date: date | None = None,
) -> ResolvedAccount:
    payload: dict[str, object] = {
        "bank": "bob",
        "variant": "easy",
        "account_number": account_number,
        "passwords": ["secret"],
        "mail": {"subjects": ["BOB"]},
        "statement": {"text_contains": [account_number]},
        "metadata": {
            "statement_date": [
                {"mode": "label_single", "label": "Statement Date :"},
            ],
        },
    }
    if opening_date is not None:
        payload["opening_date"] = opening_date
    if closing_date is not None:
        payload["closing_date"] = closing_date
    return ResolvedAccount.model_validate(payload)


def _run_context(download_path: Path) -> RunContext:
    return RunContext(
        settings=Settings(
            source=ThunderbirdSource(
                thunderbird=ThunderbirdSourceSettings(profile=Path("."))
            ),
            download_path=download_path,
            accounts=[],
            alerts=None,
            run=RunSettings(),
        ),
        reporter=NullRunReporter(),
        alerts=AlertService(handler=None),
    )


def _write_statement(
    download_path: Path,
    account: ResolvedAccount,
    month_stem: str,
    *,
    with_txt: bool = True,
) -> None:
    fy_dir = account_fy_dir(download_path, account, fy_folder_name(month_stem))
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fy_dir / f"{month_stem}.pdf"
    _ = pdf_path.write_bytes(b"%PDF-1.4")
    if with_txt:
        _ = (fy_dir / f"{month_stem}.txt").write_text("statement", encoding="utf-8")


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

        period = _build_period_covered(statements)

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

        period = _build_period_covered(statements)

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

        period = _build_period_covered(statements)

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

        period = _build_period_covered(statements)

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

        period = _build_period_covered(statements)

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

        period = _build_period_covered(statements)

        self.assertEqual(len(period.gaps), 1)
        self.assertIsNone(period.gaps[0].balances_match)

    def test_statements_without_periods_keep_months_only(self) -> None:
        statements = (
            StatementMetadata(statement_date="2024-01", formats=("pdf",)),
            StatementMetadata(statement_date="2024-02", formats=("pdf",)),
        )

        period = _build_period_covered(statements)

        self.assertEqual(period.segments, ())
        self.assertEqual(period.gaps, ())
        self.assertIsNone(period.start)
        self.assertIsNone(period.end)
        self.assertEqual(period.months, ("2023-12", "2024-01"))


class ReadAccountMetadataTests(unittest.TestCase):
    def test_read_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
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
            account = _account()
            _write_statement(download_path, account, "2024-02")

            metadata, from_file = load_account_metadata(download_path, account)

            self.assertFalse(from_file)
            self.assertEqual(metadata.statement_count, 1)
            self.assertEqual(metadata.statement_dates, ("2024-02",))

    def test_load_reads_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            _write_statement(download_path, account, "2024-03")
            refresh_account_metadata(download_path, account)

            metadata, from_file = load_account_metadata(download_path, account)

            self.assertTrue(from_file)
            self.assertEqual(metadata.statement_count, 1)


class BuildAccountMetadataTests(unittest.TestCase):
    def test_builds_from_statement_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
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
            account = ResolvedAccount.model_validate(
                {
                    "bank": "bob",
                    "variant": "easy",
                    "account_number": "5678",
                    "passwords": ["secret"],
                    "mail": {"subjects": ["BOB"]},
                    "statement": {"text_contains": ["5678"]},
                    "metadata": {
                        "statement_date": [
                            {"mode": "label_single", "label": "Statement Date :"},
                        ],
                        "balances": {
                            "opening": [
                                {
                                    "mode": "summary_table_column",
                                    "context": "Account Summary",
                                    "column": "Opening Balance",
                                }
                            ],
                            "closing": [
                                {
                                    "mode": "summary_table_column",
                                    "context": "Account Summary",
                                    "column": "Closing Balance",
                                }
                            ],
                        },
                    },
                }
            )
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
            account = _account(opening_date=date(2023, 4, 1))
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
            account = _account(opening_date=date(2023, 6, 1))
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
            account = _account(
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
            account = _account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")
            _ = (fy_dir / "transactions.csv").write_text(
                "Date,Description\n", encoding="utf-8"
            )

            metadata = build_account_metadata(download_path, account)

            self.assertEqual(metadata.formats, ("csv", "pdf", "txt"))

    def test_builds_day_level_period_from_statement_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
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

    def test_hdfc_derives_period_from_statement_date_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = ResolvedAccount.model_validate(
                {
                    "bank": "hdfc",
                    "variant": "regalia",
                    "account_number": "5678",
                    "passwords": ["secret"],
                    "mail": {"subjects": ["HDFC"]},
                    "statement": {"text_contains": ["5678"]},
                    "metadata": {
                        "statement_date": [
                            {"mode": "label_single", "label": "Statement Date"}
                        ],
                        "statement_period": {"start_day": 21},
                    },
                }
            )
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
            self.assertFalse(metadata.statements[0].period_approximate)

    def test_extracted_period_range_wins_over_statement_period_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = ResolvedAccount.model_validate(
                {
                    "bank": "hdfc",
                    "variant": "regalia",
                    "account_number": "5678",
                    "passwords": ["secret"],
                    "mail": {"subjects": ["HDFC"]},
                    "statement": {"text_contains": ["5678"]},
                    "metadata": {
                        "statement_date": [
                            {"mode": "label_single", "label": "Statement Date :"},
                            {
                                "mode": "label_range",
                                "label": "Statement Period :",
                                "joiner": " to ",
                                "take": "end",
                            },
                        ],
                        "statement_period": {"start_day": 21},
                    },
                }
            )
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


class RefreshAccountMetadataTests(unittest.TestCase):
    def test_writes_metadata_json_to_staging_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
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


class RunAccountMetadataTests(unittest.TestCase):
    def test_run_account_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            fy_dir = account_fy_dir(download_path, account, "FY23-2024")
            _ = fy_dir.mkdir(parents=True, exist_ok=True)
            _ = (fy_dir / "2024-01.pdf").write_bytes(b"%PDF")
            _ = (fy_dir / "2024-01.txt").write_text("x", encoding="utf-8")

            ctx = _run_context(download_path)
            result = run_account(ctx, account)

            metadata_path = account_metadata_path(download_path, account)
            self.assertEqual(result.output, metadata_path)
            self.assertEqual(result.statement_count, 1)
            self.assertTrue(metadata_path.is_file())
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["statement_count"], 1)
