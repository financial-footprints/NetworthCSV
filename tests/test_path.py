"""Path helper tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
    account_fy_path,
)
from networthcsv.utils.path import (
    account_fy_dir,
    account_metadata_path,
    discover_account_fy_dirs,
    fy_folder_name,
    iter_pdfs,
    pdf_path_for_txt,
    statement_pdf_path,
    txt_is_current,
    txt_path_for_pdf,
    unique_path,
)


def _settings(
    *,
    download_path: Path,
    accounts: list[ResolvedAccount],
    profile: Path = Path("/profile"),
) -> Settings:
    return Settings(
        source=ThunderbirdSource(
            thunderbird=ThunderbirdSourceSettings(profile=profile)
        ),
        download_path=download_path,
        accounts=accounts,
        alerts=None,
        run=RunSettings(),
    )


def _account(*, account_number: str = "5678") -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "account_number": account_number,
            "file_marker": account_number,
            "subjects": ["BOB"],
            "passwords": ["secret"],
        }
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
        pdf_path = Path("/data/FY23-2024/credit_card/5678/2024-01.pdf")
        self.assertEqual(
            txt_path_for_pdf(pdf_path),
            Path("/data/FY23-2024/credit_card/5678/2024-01.txt"),
        )

    def test_pdf_path_for_txt(self) -> None:
        txt_path = Path("/data/FY23-2024/credit_card/5678/2024-01.txt")
        self.assertEqual(
            pdf_path_for_txt(txt_path),
            Path("/data/FY23-2024/credit_card/5678/2024-01.pdf"),
        )

    def test_statement_pdf_path(self) -> None:
        download_path = Path("/data")
        account = _account()
        self.assertEqual(
            statement_pdf_path(download_path, account, "2024-01"),
            Path("/data/FY23-2024/credit_card/5678/2024-01.pdf"),
        )

    def test_account_fy_dir(self) -> None:
        download_path = Path("/data")
        account = _account()
        self.assertEqual(
            account_fy_dir(download_path, account, "FY23-2024"),
            Path("/data/FY23-2024/credit_card/5678"),
        )

    def test_account_metadata_path(self) -> None:
        download_path = Path("/data")
        account = _account()
        self.assertEqual(
            account_metadata_path(download_path, account),
            Path("/data/credit_card/5678/metadata.json"),
        )

    def test_discover_account_fy_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = _account()
            first = root / "FY23-2024" / "credit_card" / "5678"
            second = root / "FY24-2025" / "credit_card" / "5678"
            _ = first.mkdir(parents=True)
            _ = second.mkdir(parents=True)
            folders = discover_account_fy_dirs(root, account)
            self.assertEqual(
                [folder.parent.parent.name for folder in folders],
                ["FY23-2024", "FY24-2025"],
            )

    def test_account_fy_path(self) -> None:
        settings = _settings(
            download_path=Path("/statements"),
            accounts=[_account()],
        )
        self.assertEqual(
            account_fy_path(settings, settings.accounts[0], "FY23-2024"),
            Path("/statements/FY23-2024/credit_card/5678"),
        )

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
