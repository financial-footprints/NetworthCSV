"""ICICI ZIP upload staging and cleanup integration tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cleanup_support import account, run_context, staging_layout
from networthcsv.pipeline.cleanup.run import run
from networthcsv.pipeline.metadata import build_account_metadata
from networthcsv.pipeline.upload import save_uploaded_zip
from networthcsv.utils.path import FISCAL_YEAR_BASENAME, statement_csv_path
from zip_support import build_zip

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "icici" / "csv"


class IciciZipUploadTests(unittest.TestCase):
    def _icici_account(self):
        return account(
            bank="icici",
            variant="default",
            account_number="7788",
            text_contains=["7788"],
            opening_date="17-05-2023",
        )

    def test_zip_stages_period_based_manual_names(self) -> None:
        resolved = self._icici_account()
        fy22 = (FIXTURES / "annual-fy22-sample.csv").read_bytes()
        fy24 = (FIXTURES / "annual-sample.csv").read_bytes()
        zip_bytes = build_zip(
            {
                "export_fy22.csv": fy22,
                "export_fy24.csv": fy24,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved = staging_layout(tmp, resolved)
            paths = save_uploaded_zip(staging_dir, resolved, zip_bytes)
            self.assertEqual(len(paths), 2)
            names = {path.name for path in paths}
            self.assertTrue(all(name.startswith("manual__FY") for name in names))
            self.assertTrue(all(name.endswith(".csv") for name in names))

    def test_zip_two_annual_csvs_prepare_two_annual_canonical(self) -> None:
        resolved = self._icici_account()
        fy22 = (FIXTURES / "annual-fy22-sample.csv").read_bytes()
        fy24 = (FIXTURES / "annual-sample.csv").read_bytes()
        zip_bytes = build_zip(
            {
                "ICICI6005.csv": fy22,
                "ICICI6005_1.csv": fy24,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved = staging_layout(tmp, resolved)
            _ = save_uploaded_zip(staging_dir, resolved, zip_bytes)

            result = run(staging_dir, resolved, run_context(download_path))
            self.assertEqual(result.prepared, 2)
            self.assertEqual(result.rejected, 0)

            annual_csvs = [
                statement
                for statement in build_account_metadata(
                    download_path, resolved
                ).statements
                if statement.granularity == "annual" and "csv" in statement.formats
            ]
            self.assertEqual(len(annual_csvs), 2)
            year_keys = {statement.year_key for statement in annual_csvs}
            self.assertEqual(
                year_keys,
                {"FY22-2023", "FY24-2025"},
            )
            for statement in annual_csvs:
                csv_path = statement_csv_path(
                    download_path,
                    resolved,
                    statement.statement_date,
                )
                self.assertEqual(csv_path.name, f"{FISCAL_YEAR_BASENAME}.csv")

    def test_single_file_zip_regression(self) -> None:
        resolved = self._icici_account()
        fy24 = (FIXTURES / "annual-sample.csv").read_bytes()
        zip_bytes = build_zip({"ICICI6005_1.csv": fy24})
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved = staging_layout(tmp, resolved)
            paths = save_uploaded_zip(staging_dir, resolved, zip_bytes)
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].name.startswith("manual__FY"))

            result = run(staging_dir, resolved, run_context(download_path))
            self.assertEqual((result.prepared, result.rejected), (1, 0))
            period = paths[0].name.removeprefix("manual__").removesuffix(".csv")
            self.assertTrue(
                statement_csv_path(download_path, resolved, period).is_file()
            )


if __name__ == "__main__":
    _ = unittest.main()
