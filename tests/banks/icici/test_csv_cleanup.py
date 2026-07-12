"""ICICI CSV cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import account, run_context, staging_layout
from networthcsv.pipeline.cleanup import run
from networthcsv.pipeline.cleanup.canonical import remove_ineligible_canonical_outputs
from networthcsv.pipeline.cleanup.grouping import collect_csv_groups
from networthcsv.pipeline.cleanup.prepare_csv_month import prepare_csv_month
from networthcsv.utils.path import statement_csv_path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "icici" / "csv"


class IciciCsvCleanupTests(unittest.TestCase):
    def test_monthly_csv_lands_in_canonical_path(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="6655",
            text_contains=["6655"],
            opening_date="01-01-2020",
        )
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, _ = staging_layout(tmp, resolved)
            staging_csv = staging_dir / "INBOX__2026-04-10.csv"
            _ = staging_csv.write_text(text, encoding="utf-8")

            collected = collect_csv_groups(staging_dir, resolved)
            self.assertIn("2026-04", collected.groups)

            prepared, rejected = prepare_csv_month(
                staging_dir,
                download_path,
                "2026-04",
                collected.groups["2026-04"],
                resolved,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            self.assertEqual(prepared, 1)
            self.assertEqual(rejected, 0)
            out = statement_csv_path(download_path, resolved, "2026-04")
            self.assertTrue(out.is_file())
            self.assertFalse(staging_csv.exists())

    def test_annual_csv_lands_in_annual_path(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="7788",
            text_contains=["7788"],
            opening_date="17-05-2023",
        )
        text = (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, _ = staging_layout(tmp, resolved)
            staging_csv = staging_dir / "INBOX__2024-05-20__annual.csv"
            _ = staging_csv.write_text(text, encoding="utf-8")

            collected = collect_csv_groups(staging_dir, resolved)
            self.assertEqual(len(collected.groups), 1)
            period = next(iter(collected.groups))
            self.assertEqual(period, "FY24-2025")

            prepared, rejected = prepare_csv_month(
                staging_dir,
                download_path,
                period,
                collected.groups[period],
                resolved,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            self.assertEqual(prepared, 1)
            self.assertEqual(rejected, 0)
            out = statement_csv_path(download_path, resolved, period)
            self.assertTrue(out.is_file())
            self.assertEqual(out.name, "fiscal_year.csv")

    def test_manual_period_staging_honored_for_csv(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="6655",
            text_contains=["6655"],
            opening_date="01-01-2020",
        )
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, _ = staging_layout(tmp, resolved)
            staging_csv = staging_dir / "manual__2026-04.csv"
            _ = staging_csv.write_text(text, encoding="utf-8")

            collected = collect_csv_groups(staging_dir, resolved)
            self.assertEqual(collected.path_period_source[staging_csv], "manual")
            self.assertIn("2026-04", collected.groups)

    def test_ambiguous_csv_keeper_picks_deterministic_path(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="7788",
            text_contains=["7788"],
            opening_date="17-05-2023",
        )
        text = (FIXTURES / "annual-sample.csv").read_text(encoding="utf-8")
        variant = text.replace("1,763.51", "1,763.52")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, _ = staging_layout(tmp, resolved)
            first = staging_dir / "INBOX__2024-05-20__annual.csv"
            second = staging_dir / "INBOX__2024-05-21__annual.csv"
            _ = first.write_text(text, encoding="utf-8")
            _ = second.write_text(variant, encoding="utf-8")

            collected = collect_csv_groups(staging_dir, resolved)
            period = next(iter(collected.groups))
            prepared, rejected = prepare_csv_month(
                staging_dir,
                download_path,
                period,
                collected.groups[period],
                resolved,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            out = statement_csv_path(download_path, resolved, period)
            self.assertTrue(out.is_file())

    def test_rejects_csv_with_text_not_contains_marker(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="6655",
            text_contains=["6655"],
            text_not_contains=["MESSAGE Details:"],
            opening_date="01-01-2020",
        )
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, _ = staging_layout(tmp, resolved)
            staging_csv = staging_dir / "INBOX__2026-04-10.csv"
            _ = staging_csv.write_text(text, encoding="utf-8")

            collected = collect_csv_groups(staging_dir, resolved)
            prepared, rejected = prepare_csv_month(
                staging_dir,
                download_path,
                "2026-04",
                collected.groups["2026-04"],
                resolved,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(staging_csv.exists())
            self.assertFalse(
                statement_csv_path(download_path, resolved, "2026-04").is_file()
            )

    @patch("networthcsv.pipeline.cleanup.staging.decrypt_pdfs_in_place", return_value=0)
    def test_run_prunes_excluded_csv_staging(self, _mock_decrypt: MagicMock) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="6655",
            text_contains=["6655"],
            text_not_contains=["MESSAGE Details:"],
            opening_date="01-01-2020",
        )
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved = staging_layout(tmp, resolved)
            staging_csv = staging_dir / "attachment.csv"
            _ = staging_csv.write_text(text, encoding="utf-8")

            result = run(staging_dir, resolved, run_context(download_path))

            self.assertFalse(staging_csv.exists())
            self.assertEqual(result.prepared, 0)

    def test_remove_ineligible_canonical_csv(self) -> None:
        resolved = account(
            bank="icici",
            variant="default",
            account_number="6655",
            text_contains=["6655"],
            text_not_contains=["MESSAGE Details:"],
            opening_date="01-01-2020",
        )
        text = (FIXTURES / "monthly-sample.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved = staging_layout(tmp, resolved)
            csv_out = statement_csv_path(download_path, resolved, "2026-04")
            _ = csv_out.parent.mkdir(parents=True, exist_ok=True)
            _ = csv_out.write_text(text, encoding="utf-8")

            removed = remove_ineligible_canonical_outputs(download_path, resolved)

            self.assertEqual(removed, 1)
            self.assertFalse(csv_out.is_file())


if __name__ == "__main__":
    _ = unittest.main()
