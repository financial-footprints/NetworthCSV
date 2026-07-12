"""IndusInd cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import FIXTURES_ROOT, account, run_context, staging_layout
from networthcsv.pipeline.cleanup import prepare_month, run
from networthcsv.utils.banks import get_handler
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf


class IndusindAnnualSummaryCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_deletes_annual_summary_staging_pdf_using_handler_defaults(
        self, mock_extract: MagicMock
    ) -> None:
        summary_text = (FIXTURES_ROOT / "indusind/annual-spend-summary.txt").read_text(
            encoding="utf-8"
        )
        resolved_account = account(
            bank="indusind",
            variant="auraedge",
            text_contains=["5621"],
            account_number="5621",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "INBOX__2024-06-29.pdf")
            mock_extract.return_value = summary_text

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-06",
                [staging],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2024-06")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertFalse(staging.is_file())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_deletes_spaced_annual_summary_markers(
        self, mock_extract: MagicMock
    ) -> None:
        summary_text = (
            FIXTURES_ROOT / "indusind/annual-spend-summary-spaced.txt"
        ).read_text(encoding="utf-8")
        resolved_account = account(
            bank="indusind",
            variant="auraedge",
            text_contains=["9183"],
            account_number="9183",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "INBOX__2024-06-29.pdf")
            mock_extract.return_value = summary_text

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-06",
                [staging],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(staging.is_file())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_handler_exclusion_survives_empty_text_not_contains(
        self, mock_extract: MagicMock
    ) -> None:
        summary_text = (FIXTURES_ROOT / "indusind/annual-spend-summary.txt").read_text(
            encoding="utf-8"
        )
        resolved_account = account(
            bank="indusind",
            variant="auraedge",
            text_contains=["5621"],
            text_not_contains=[],
            account_number="5621",
        )
        self.assertEqual(resolved_account.statement.text_not_contains, [])
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "INBOX__2024-06-29.pdf")
            mock_extract.return_value = summary_text

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-06",
                [staging],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(staging.is_file())

    @patch("networthcsv.pipeline.cleanup.staging.decrypt_pdfs_in_place", return_value=0)
    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_run_prunes_excluded_unknown_month_staging(
        self, mock_extract: MagicMock, _mock_decrypt: MagicMock
    ) -> None:
        summary_text = (
            FIXTURES_ROOT / "indusind/annual-spend-summary-spaced.txt"
        ).read_text(encoding="utf-8")
        resolved_account = account(
            bank="indusind",
            variant="auraedge",
            text_contains=["9183"],
            account_number="9183",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "attachment.pdf")
            mock_extract.return_value = summary_text

            result = run(staging_dir, resolved_account, run_context(download_path))

            self.assertFalse(staging.is_file())
            self.assertEqual(result.prepared, 0)

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_promotes_real_indusind_statement_using_handler_defaults(
        self, mock_extract: MagicMock
    ) -> None:
        statement_text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        resolved_account = account(
            bank="indusind",
            variant="auraedge",
            text_contains=["3856"],
            account_number="3856",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "INBOX__2021-03-06.pdf")
            mock_extract.return_value = statement_text

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2021-02",
                [staging],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2021-02")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.is_file())


class IndusindExcludedStatementTests(unittest.TestCase):
    def test_is_excluded_statement_matches_spaced_markers(self) -> None:
        handler = get_handler("indusind", "auraedge")
        spaced = (FIXTURES_ROOT / "indusind/annual-spend-summary-spaced.txt").read_text(
            encoding="utf-8"
        )
        self.assertTrue(handler.is_excluded_statement(spaced))

    def test_is_excluded_statement_allows_real_statement(self) -> None:
        handler = get_handler("indusind", "auraedge")
        statement_text = (FIXTURES_ROOT / "indusind/auraedge/sample.txt").read_text(
            encoding="utf-8"
        )
        self.assertFalse(handler.is_excluded_statement(statement_text))


if __name__ == "__main__":
    _ = unittest.main()
