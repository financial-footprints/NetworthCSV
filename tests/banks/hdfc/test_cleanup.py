"""HDFC cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import FIXTURES_ROOT, account, extract_side_effect, staging_layout
from networthcsv.pipeline.cleanup.cleanup import collect_month_groups, prepare_month
from networthcsv.pipeline.cleanup.statement_date import PeriodSource
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf


class HdfcInboxCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_yearly_inbox_sibling_lands_in_yearly_period(
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
            yearly_period = "yearly-2024-04_2025-03"
            self.assertIn(yearly_period, collected.groups)
            self.assertIn("2026-05", collected.groups)
            self.assertEqual(
                collected.path_period_source[yearly_pdf],
                "yearly",
            )
            self.assertEqual(
                collected.path_period_source[sibling],
                "filename_fallback",
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                yearly_period,
                collected.groups[yearly_period],
                resolved_account,
                raw_by_path=collected.raw_by_path,
                path_month=collected.path_month,
                path_hash=collected.path_hash,
                path_period_source=collected.path_period_source,
            )
            yearly_out = statement_pdf_path(
                download_path, resolved_account, yearly_period
            )
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(yearly_out.is_file())
            self.assertTrue(txt_path_for_pdf(yearly_out).is_file())
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

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_prefers_yearly_confidence_over_filename_fallback(
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
            period = "yearly-2024-04_2025-03"
            path_period_source: dict[Path, PeriodSource] = {
                yearly_pdf: "yearly",
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


if __name__ == "__main__":
    _ = unittest.main()
