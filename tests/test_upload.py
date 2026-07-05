"""Manual upload helper tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from networthcsv.pipeline.metadata.metadata import build_account_metadata
from networthcsv.pipeline.upload import (
    StatementFileExistsError,
    month_stem_from_manual_upload,
    save_uploaded_csv,
    save_uploaded_pdf,
)
from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
    account_download_path,
)
from networthcsv.utils.path import statement_csv_path, statement_pdf_path


def _account() -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "account_number": "5678",
            "passwords": ["secret"],
            "mail": {"subjects": ["BOB"]},
            "statement": {"text_contains": ["5678"]},
        }
    )


def _settings(download_path: Path) -> Settings:
    return Settings(
        source=ThunderbirdSource(
            thunderbird=ThunderbirdSourceSettings(profile=Path("."))
        ),
        download_path=download_path,
        accounts=[],
        alerts=None,
        run=RunSettings(),
    )


class UploadHelperTests(unittest.TestCase):
    def test_month_stem_from_manual_upload(self) -> None:
        self.assertEqual(
            month_stem_from_manual_upload("manual__2024-02.pdf"),
            "2024-02",
        )
        self.assertIsNone(month_stem_from_manual_upload("INBOX__2024-01-21.pdf"))
        self.assertIsNone(month_stem_from_manual_upload("manual__bad-name.pdf"))

    def test_save_uploaded_pdf_writes_staging_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            settings = _settings(download_path)
            staging_dir = account_download_path(settings, account)
            path = save_uploaded_pdf(
                staging_dir,
                download_path,
                account,
                "2024-02",
                b"%PDF-1.4",
            )
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "manual__2024-02.pdf")

    def test_save_uploaded_pdf_rejects_existing_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            canonical = statement_pdf_path(download_path, account, "2024-02")
            _ = canonical.parent.mkdir(parents=True, exist_ok=True)
            _ = canonical.write_bytes(b"%PDF")
            settings = _settings(download_path)
            staging_dir = account_download_path(settings, account)
            _ = staging_dir.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(StatementFileExistsError):
                _ = save_uploaded_pdf(
                    staging_dir,
                    download_path,
                    account,
                    "2024-02",
                    b"%PDF-1.4",
                )

    def test_save_uploaded_csv_writes_fy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            path = save_uploaded_csv(
                download_path,
                account,
                "2024-02",
                b"Date,Amount\n2024-01-01,1.00\n",
            )
            expected = statement_csv_path(download_path, account, "2024-02")
            self.assertEqual(path, expected)
            self.assertTrue(expected.is_file())

    def test_metadata_includes_csv_only_statement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            _ = save_uploaded_csv(
                download_path,
                account,
                "2024-02",
                b"Date,Amount\n",
            )
            metadata = build_account_metadata(download_path, account)
            self.assertEqual(metadata.statement_count, 1)
            self.assertEqual(metadata.statements[0].statement_date, "2024-02")
            self.assertEqual(metadata.statements[0].formats, ("csv",))


if __name__ == "__main__":
    _ = unittest.main()
