"""Path helper tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from src.core.paths import fy_folder_name, txt_is_current, txt_path_for_pdf, unique_path


class PathTests(unittest.TestCase):
    def test_unique_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = unique_path(directory, "2024-01.pdf")
            first.write_text("a", encoding="utf-8")
            second = unique_path(directory, "2024-01.pdf")
            self.assertEqual(second.name, "2024-01 (1).pdf")

    def test_fy_folder_name_april_boundary(self) -> None:
        self.assertEqual(fy_folder_name("2024-03"), "FY23-2024")
        self.assertEqual(fy_folder_name("2024-04"), "FY24-2025")
        self.assertEqual(fy_folder_name("unknown-month"), "unknown-month")

    def test_txt_path_for_pdf(self) -> None:
        download_dir = Path("/data/bob")
        fy_dir = Path("/data/bob/FY23-2024")
        pdf_path = Path("/data/bob/FY23-2024/2024-01.pdf")
        self.assertEqual(
            txt_path_for_pdf(download_dir, fy_dir, pdf_path),
            Path("/data/bob/txt/FY23-2024/2024-01.txt"),
        )

    def test_txt_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "2024-01.pdf"
            txt_path = root / "2024-01.txt"
            pdf_path.write_text("pdf", encoding="utf-8")
            self.assertFalse(txt_is_current(pdf_path, txt_path))
            txt_path.write_text("txt", encoding="utf-8")
            self.assertTrue(txt_is_current(pdf_path, txt_path))
            time.sleep(0.01)
            pdf_path.write_text("newer", encoding="utf-8")
            self.assertFalse(txt_is_current(pdf_path, txt_path))


if __name__ == "__main__":
    unittest.main()
