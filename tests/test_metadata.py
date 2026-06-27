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
) -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "account_number": account_number,
            "file_marker": account_number,
            "subjects": ["BOB"],
            "passwords": ["secret"],
            "opening_date": opening_date,
            "statement_date_markers": [
                {"mode": "label_single", "label": "Statement Date :"},
            ],
        }
    )


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
                    "file_marker": "5678",
                    "subjects": ["BOB"],
                    "passwords": ["secret"],
                    "statement_date_markers": [
                        {"mode": "label_single", "label": "Statement Date :"},
                    ],
                    "balance_markers": {
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

            self.assertEqual(metadata.period_covered.start, "2023-03")
            self.assertEqual(metadata.period_covered.end, "2023-06")
            self.assertEqual(
                metadata.period_covered.months,
                ("2023-03", "2023-04", "2023-05", "2023-06"),
            )

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
