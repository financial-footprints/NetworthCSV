"""Path helper tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from src.utils.paths import (
    discover_fy_folders,
    fy_folder_name,
    iter_pdfs,
    pdf_path_for_txt,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
    unique_path,
)


class PathTests(unittest.TestCase):
    def test_unique_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = unique_path(directory, "2024-01.pdf")
            _ = first.write_text("a", encoding="utf-8")
            second = unique_path(directory, "2024-01.pdf")
            self.assertEqual(second.name, "2024-01 (1).pdf")

    def test_fy_folder_name_april_boundary(self) -> None:
        self.assertEqual(fy_folder_name("2024-03"), "FY23-2024")
        self.assertEqual(fy_folder_name("2024-04"), "FY24-2025")
        self.assertEqual(fy_folder_name("unknown-month"), "unknown-month")

    def test_txt_path_for_pdf(self) -> None:
        download_dir = Path("/data/bob/easy")
        pdf_path = Path("/data/bob/easy/FY23-2024/2024-01.pdf")
        self.assertEqual(
            txt_path_for_pdf(download_dir, pdf_path),
            Path("/data/bob/easy/FY23-2024/2024-01.txt"),
        )

    def test_pdf_path_for_txt(self) -> None:
        download_dir = Path("/data/bob/easy")
        txt_path = Path("/data/bob/easy/FY23-2024/2024-01.txt")
        self.assertEqual(
            pdf_path_for_txt(download_dir, txt_path),
            Path("/data/bob/easy/FY23-2024/2024-01.pdf"),
        )

    def test_statement_pdf_path(self) -> None:
        download_dir = Path("/data/bob/easy")
        self.assertEqual(
            statement_pdf_path(download_dir, "2024-01"),
            Path("/data/bob/easy/FY23-2024/2024-01.pdf"),
        )

    def test_discover_fy_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            _ = (download_dir / "FY23-2024").mkdir(parents=True)
            _ = (download_dir / "FY24-2025").mkdir()
            folders = discover_fy_folders(download_dir)
            self.assertEqual([folder.name for folder in folders], ["FY23-2024", "FY24-2025"])

    def test_txt_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "2024-01.pdf"
            txt_path = root / "2024-01.txt"
            _ = pdf_path.write_text("pdf", encoding="utf-8")
            self.assertFalse(txt_is_current(pdf_path, txt_path))
            _ = txt_path.write_text("txt", encoding="utf-8")
            self.assertTrue(txt_is_current(pdf_path, txt_path))
            time.sleep(0.01)
            _ = pdf_path.write_text("newer", encoding="utf-8")
            self.assertFalse(txt_is_current(pdf_path, txt_path))


class IterPdfsTests(unittest.TestCase):
    def test_finds_mixed_pdf_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            lower = directory / "2024-01.pdf"
            upper = directory / "All Mail__2024-02-21.PDF"
            other = directory / "readme.txt"
            _ = lower.write_bytes(b"%PDF-1.4")
            _ = upper.write_bytes(b"%PDF-1.4")
            _ = other.write_text("notes", encoding="utf-8")

            found = list(iter_pdfs(directory))

            self.assertEqual(found, [lower, upper])


if __name__ == "__main__":
    _ = unittest.main()
