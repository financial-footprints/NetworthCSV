"""ICICI cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import account, extract_side_effect, staging_layout
from networthcsv.pipeline.cleanup.cleanup import prepare_month
from networthcsv.utils.path import statement_pdf_path

_ICICI_REISSUE_STATEMENT = """\
           STATEMENT DATE
          February 12, 2023
          PAYMENT DUE DATE
          March 2, 2023
                            STATEMENT SUMMARY
           Total Amount due
              275.50
            SPENDS OVERVIEW
                             4315XXXXXXXX6005
     Statement period : January 13, 2023 to February 12, 2023
                               Previous Balance Purchases / Charges Cash Advances Payments / Credits
                                  0.00       4,120.19      0.00       3,844.69
"""


class IciciReissuedStatementCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str, *, payload: bytes) -> Path:
        path = directory / name
        _ = path.write_bytes(payload)
        return path

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
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


if __name__ == "__main__":
    _ = unittest.main()
