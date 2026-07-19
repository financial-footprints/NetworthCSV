"""ICICI cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers import FIXTURES_ROOT, account, extract_side_effect, staging_layout
from networthcsv.pipeline.cleanup import prepare_month
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf

_FIXTURES = FIXTURES_ROOT / "icici" / "amazon"
_MULTICOLUMN = (_FIXTURES / "multicolumn_earnings_first.txt").read_text(
    encoding="utf-8"
)

_ICICI_REISSUE_STATEMENT = """\
           STATEMENT DATE
          February 12, 2023
          PAYMENT DUE DATE
          March 2, 2023
                            STATEMENT SUMMARY
Invoice No: 2093021200016005
           Total Amount due
              275.50
            SPENDS OVERVIEW
                             4315XXXXXXXX6005
                             15/01/2023 88472910561 SAMPLE MERCHANT PURCHASE IN 275.50
     Statement period : January 13, 2023 to February 12, 2023
                               Previous Balance Purchases / Charges Cash Advances Payments / Credits
                                  0.00       4,120.19      0.00       3,844.69
"""


class IciciReissuedStatementCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str, *, payload: bytes) -> Path:
        path = directory / name
        _ = path.write_bytes(payload)
        return path

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_reissued_statement_prefers_later_email_date(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="icici",
            variant="amazon",
            text_contains="4315XXXXXXXX6005",
            account_number="6005",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            feb15 = self._write_pdf(
                staging_dir,
                "Important__2023-02-15.pdf",
                payload=b"%PDF-1.4\nfeb-15-statement-bytes",
            )
            feb18 = self._write_pdf(
                staging_dir,
                "Important__2023-02-18.pdf",
                payload=b"%PDF-1.4\nfeb-18-statement-bytes",
            )
            expected_bytes = b"%PDF-1.4\nfeb-18-statement-bytes"
            mock_extract.side_effect = extract_side_effect(
                {
                    feb15: _ICICI_REISSUE_STATEMENT,
                    feb18: _ICICI_REISSUE_STATEMENT,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-02",
                [feb15, feb18],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2023-02")
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertEqual(pdf_out.read_bytes(), expected_bytes)
            self.assertFalse(feb15.exists())
            self.assertFalse(feb18.exists())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_same_invoice_equal_richness_same_email_date_stays_ambiguous(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="icici",
            variant="amazon",
            text_contains=["4315XXXXXXXX6005"],
            account_number="6005",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            first = self._write_pdf(
                staging_dir,
                "All Mail__2022-09-13.pdf",
                payload=b"%PDF-1.4\nfirst",
            )
            second = self._write_pdf(
                staging_dir,
                "All Mail__2022-09-13 (1).pdf",
                payload=b"%PDF-1.4\nsecond",
            )
            mock_extract.side_effect = extract_side_effect(
                {
                    first: _ICICI_REISSUE_STATEMENT,
                    second: _ICICI_REISSUE_STATEMENT,
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-02",
                [first, second],
                resolved_account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    @patch("networthcsv.utils.pdf.extract_pdf_text_plumber")
    def test_multicolumn_statement_prepares_with_invoice_in_txt(
        self, mock_extract: MagicMock
    ) -> None:
        resolved_account = account(
            bank="icici",
            variant="amazon",
            text_contains=["123454XXXXXX7890"],
            account_number="7148",
        )
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, resolved_account = staging_layout(
                tmp, resolved_account
            )
            staging = self._write_pdf(
                staging_dir,
                "All Mail__2022-09-13.pdf",
                payload=b"%PDF-1.4\nmulticolumn",
            )
            mock_extract.return_value = _MULTICOLUMN

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2022-09",
                [staging],
                resolved_account,
            )

            pdf_out = statement_pdf_path(download_path, resolved_account, "2022-09")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())
            txt_content = txt_out.read_text(encoding="utf-8")
            self.assertIn("Invoice No: 2099120900019246", txt_content)
            self.assertIn("123454XXXXXX7890", txt_content)
            self.assertNotIn("SPENDS OVERVIEW", txt_content)
            self.assertNotIn("# International Spends", txt_content)


if __name__ == "__main__":
    _ = unittest.main()
