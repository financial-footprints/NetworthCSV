"""PNB cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import FIXTURES_ROOT, account, extract_side_effect, staging_layout
from networthcsv.pipeline.cleanup import prepare_month
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf

_V2_FIXTURE = (
    FIXTURES_ROOT / "pnb" / "platinum" / "layout_marketing_prefix.txt"
).read_text(encoding="utf-8")

_V2_MINIMAL = """\
Invoice No :
2024CC0100999
Card No :
441299XXXXXX5678
Invoice Date :
16-MAR-2024
********** End of Statement **********
"""

_V2_DIFFERENT_INVOICE = _V2_FIXTURE.replace("2024CC0100999", "2024CC0199888")


class PnbSanitizedTextCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_identifier_must_appear_in_sanitized_text(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(bank="pnb", variant=None)
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = (
                "junk\n5678\n********** End of Statement **********"
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertIn("5678", txt_out.read_text(encoding="utf-8"))

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_v2_marketing_layout_prepares_statement(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="pnb",
            variant="platinum",
            text_contains=["441299XXXXXX5678"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(staging_dir, "All Mail__2024-03-19.pdf")
            mock_extract.return_value = _V2_FIXTURE

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-03",
                [staging],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2024-03")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())
            self.assertIn("441299XXXXXX5678", txt_out.read_text(encoding="utf-8"))

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_v2_reissued_duplicate_keeps_newer_email(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="pnb",
            variant="platinum",
            text_contains=["441299XXXXXX5678"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            older = self._write_pdf(staging_dir, "All Mail__2024-03-19.pdf")
            newer = self._write_pdf(staging_dir, "All Mail__2026-07-18 (4).pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    older: _V2_FIXTURE,
                    newer: _V2_FIXTURE,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-03",
                [older, newer],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2024-03")
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertFalse(older.exists())
            self.assertFalse(newer.exists())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_same_invoice_richer_parse_wins(self, mock_extract: MagicMock) -> None:
        resolved_account = account(
            bank="pnb",
            variant="platinum",
            text_contains=["441299XXXXXX5678"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            sparse = self._write_pdf(staging_dir, "All Mail__2024-03-19.pdf")
            rich = self._write_pdf(staging_dir, "All Mail__2026-07-18.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    sparse: _V2_MINIMAL,
                    rich: _V2_FIXTURE,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-03",
                [sparse, rich],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2024-03")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(txt_out.is_file())
            self.assertIn("17-FEB-2024", txt_out.read_text(encoding="utf-8"))
            self.assertFalse(sparse.exists())
            self.assertFalse(rich.exists())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_same_invoice_equal_richness_same_email_date_stays_ambiguous(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="pnb",
            variant="platinum",
            text_contains=["441299XXXXXX5678"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            first = self._write_pdf(staging_dir, "All Mail__2024-03-19.pdf")
            second = self._write_pdf(staging_dir, "INBOX__2024-03-19.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    first: _V2_FIXTURE,
                    second: _V2_FIXTURE,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-03",
                [first, second],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_different_invoices_stay_ambiguous(self, mock_extract: MagicMock) -> None:
        resolved_account = account(
            bank="pnb",
            variant="platinum",
            text_contains=["441299XXXXXX5678"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            first = self._write_pdf(staging_dir, "All Mail__2024-03-19.pdf")
            second = self._write_pdf(staging_dir, "All Mail__2026-07-18.pdf")
            mock_extract.side_effect = extract_side_effect(
                {
                    first: _V2_FIXTURE,
                    second: _V2_DIFFERENT_INVOICE,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-03",
                [first, second],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())


if __name__ == "__main__":
    _ = unittest.main()
