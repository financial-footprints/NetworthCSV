"""PNB cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import account, staging_layout
from networthcsv.pipeline.cleanup import prepare_month
from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf


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


if __name__ == "__main__":
    _ = unittest.main()
