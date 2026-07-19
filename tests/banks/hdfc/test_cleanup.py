"""HDFC cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers import FIXTURES_ROOT, account, extract_side_effect, staging_layout
from networthcsv.pipeline.cleanup import (
    PeriodSource,
    collect_month_groups,
    prepare_month,
)
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf


class HdfcInboxCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_annual_inbox_sibling_lands_in_annual_period(
        self, mock_extract: MagicMock
    ) -> None:
        yearly_text = (FIXTURES_ROOT / "hdfc/default/yearly-sample.txt").read_text(
            encoding="utf-8"
        )
        resolved_account = account(
            bank="hdfc",
            variant="default",
            text_contains="XXXXXX7890",
            account_number="7890",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            yearly_pdf = self._write_pdf(staging_dir, "INBOX__2026-05-20 (1).pdf")
            sibling = self._write_pdf(staging_dir, "INBOX__2026-05-20 (2).pdf")
            bare = self._write_pdf(staging_dir, "INBOX__2026-05-20.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    yearly_pdf: yearly_text,
                    sibling: "HDFC card 000123456XXXXXX7890 generic monthly text",
                    bare: "HDFC card 000123456XXXXXX7890 other attachment",
                }
            )

            collected = collect_month_groups(staging_dir, resolved_account)
            annual_period = "FY24-2025"
            self.assertIn(annual_period, collected.groups)
            self.assertIn("2026-05", collected.groups)
            self.assertEqual(
                collected.path_period_source[yearly_pdf],
                "annual",
            )
            self.assertEqual(
                collected.path_period_source[sibling],
                "filename_fallback",
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                annual_period,
                collected.groups[annual_period],
                resolved_account,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            annual_out = statement_pdf_path(
                download_path, resolved_account, annual_period
            )
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(annual_out.is_file())
            self.assertTrue(txt_path_for_pdf(annual_out).is_file())
            self.assertFalse(yearly_pdf.exists())

            month_prepared, month_rejected = prepare_month(
                staging_dir,
                download_path,
                "2026-05",
                collected.groups["2026-05"],
                resolved_account,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            self.assertEqual((month_prepared, month_rejected), (0, 1))
            self.assertTrue(sibling.is_file())
            self.assertTrue(bare.is_file())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_prefers_annual_confidence_over_filename_fallback(
        self, mock_extract: MagicMock
    ) -> None:
        yearly_text = (FIXTURES_ROOT / "hdfc/default/yearly-sample.txt").read_text(
            encoding="utf-8"
        )
        resolved_account = account(
            bank="hdfc",
            variant="default",
            text_contains="XXXXXX7890",
            account_number="7890",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            yearly_pdf = self._write_pdf(staging_dir, "INBOX__2026-05-20 (1).pdf")
            fallback_pdf = self._write_pdf(staging_dir, "INBOX__2026-05-20.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    yearly_pdf: yearly_text,
                    fallback_pdf: yearly_text,
                }
            )
            period = "FY24-2025"
            path_period_source: dict[Path, PeriodSource] = {
                yearly_pdf: "annual",
                fallback_pdf: "filename_fallback",
            }

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                period,
                [yearly_pdf, fallback_pdf],
                resolved_account,
                path_period_source=path_period_source,
            )

            self.assertEqual((prepared, rejected), (1, 0))
            txt_out = txt_path_for_pdf(
                statement_pdf_path(download_path, resolved_account, period)
            )
            self.assertTrue(txt_out.is_file())
            self.assertFalse(yearly_pdf.exists())
            self.assertFalse(fallback_pdf.exists())


class HdfcSwiggyDuplicateCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_modern_and_duplicate_statement_collapse_for_month(
        self, mock_extract: MagicMock
    ) -> None:
        modern_text = (FIXTURES_ROOT / "hdfc/swiggy/modern-may-2026.txt").read_text(
            encoding="utf-8"
        )
        duplicate_text = (
            FIXTURES_ROOT / "hdfc/swiggy/duplicate-may-2026.txt"
        ).read_text(encoding="utf-8")
        resolved_account = account(
            bank="hdfc",
            variant="swiggy",
            text_contains=["123454XXXXXX7890"],
            account_number="5678",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            original = self._write_pdf(staging_dir, "INBOX__2026-05-21.pdf")
            duplicate = self._write_pdf(staging_dir, "INBOX__2026-07-11.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    original: modern_text,
                    duplicate: duplicate_text,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2026-05",
                [original, duplicate],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2026-05")
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertFalse(original.exists())
            self.assertFalse(duplicate.exists())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_aan_collapses_even_when_modern_closing_missing(
        self, mock_extract: MagicMock
    ) -> None:
        modern_text = (FIXTURES_ROOT / "hdfc/swiggy/modern-may-2026.txt").read_text(
            encoding="utf-8"
        )
        # Simulate live extract where the modern TOTAL AMOUNT DUE block is absent.
        modern_text = modern_text.replace(
            "TOTAL AMOUNT DUE\nC277.00\nMINIMUM DUE\nC200.00\n",
            "",
        )
        duplicate_text = (
            FIXTURES_ROOT / "hdfc/swiggy/duplicate-may-2026.txt"
        ).read_text(encoding="utf-8")
        resolved_account = account(
            bank="hdfc",
            variant="swiggy",
            text_contains=["123454XXXXXX7890"],
            account_number="5678",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            original = self._write_pdf(staging_dir, "INBOX__2026-05-21.pdf")
            duplicate = self._write_pdf(staging_dir, "INBOX__2026-07-11.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    original: modern_text,
                    duplicate: duplicate_text,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2026-05",
                [original, duplicate],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (1, 0))
            self.assertFalse(original.exists())
            self.assertFalse(duplicate.exists())


if __name__ == "__main__":
    _ = unittest.main()
