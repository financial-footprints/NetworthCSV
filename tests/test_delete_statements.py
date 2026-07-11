"""Delete pipeline output tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from networthcsv.pipeline.delete_statements.delete import (
    _build_parser,
    collect_account_output_paths,
    delete_account_statements,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.path import account_fy_dir, account_metadata_path, fy_folder_name


def _account(*, account_number: str = "5678") -> ResolvedAccount:
    handler = get_handler("bob", "easy")
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "account_number": account_number,
            "passwords": ["secret"],
            **defaults.model_dump(),
            "statement": {
                **defaults.statement.model_dump(),
                "text_contains": [account_number],
            },
        }
    )


def _write_cleanup_outputs(
    download_path: Path,
    account: ResolvedAccount,
    month_stem: str,
    *,
    with_txt: bool = True,
) -> None:
    fy_dir = account_fy_dir(download_path, account, fy_folder_name(month_stem))
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fy_dir / f"{month_stem}.pdf"
    _ = pdf_path.write_bytes(b"%PDF-1.4")
    if with_txt:
        _ = (fy_dir / f"{month_stem}.txt").write_text("statement", encoding="utf-8")


class CollectAccountOutputPathsTests(unittest.TestCase):
    def test_collects_cleanup_metadata_and_parse_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            staging_dir = download_path / "credit_card" / account.account_number
            _ = staging_dir.mkdir(parents=True)
            _ = (staging_dir / "unparsed.pdf").write_bytes(b"%PDF-1.4")
            _ = (staging_dir / "metadata.json").write_text("{}", encoding="utf-8")
            _write_cleanup_outputs(download_path, account, "2024-05")
            fy_dir = account_fy_dir(download_path, account, fy_folder_name("2024-05"))
            _ = (fy_dir / "2024-05.csv").write_text("date,amount\n", encoding="utf-8")
            _ = (fy_dir / "transactions.csv").write_text(
                "date,amount\n", encoding="utf-8"
            )

            paths = collect_account_output_paths(download_path, account)
            names = {path.name for path in paths}

            self.assertEqual(
                names,
                {
                    "2024-05.csv",
                    "2024-05.pdf",
                    "2024-05.txt",
                    "metadata.json",
                    "transactions.csv",
                },
            )


class DeleteAccountStatementsTests(unittest.TestCase):
    def test_deletes_cleanup_metadata_and_parse_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            account = _account()
            staging_dir = download_path / "credit_card" / account.account_number
            _ = staging_dir.mkdir(parents=True)
            _ = (staging_dir / "manual__2024-05.pdf").write_bytes(b"%PDF-1.4")
            _write_cleanup_outputs(download_path, account, "2024-05")
            fy_dir = account_fy_dir(download_path, account, fy_folder_name("2024-05"))
            _ = (fy_dir / "2024-05.csv").write_text("date,amount\n", encoding="utf-8")
            _ = (fy_dir / "transactions.csv").write_text(
                "date,amount\n", encoding="utf-8"
            )
            metadata_path = account_metadata_path(download_path, account)
            _ = metadata_path.write_text(
                json.dumps({"statement_count": 99}),
                encoding="utf-8",
            )

            result = delete_account_statements(download_path, account)

            self.assertEqual(result.files_removed, 5)
            self.assertEqual(result.dirs_removed, 1)
            self.assertTrue((staging_dir / "manual__2024-05.pdf").is_file())
            self.assertFalse(metadata_path.exists())
            self.assertFalse(fy_dir.exists())

    def test_leaves_other_accounts_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            target = _account(account_number="5678")
            other = _account(account_number="9999")
            _write_cleanup_outputs(download_path, target, "2024-05")
            _write_cleanup_outputs(download_path, other, "2024-05")

            _ = delete_account_statements(download_path, target)

            other_pdf = (
                account_fy_dir(download_path, other, fy_folder_name("2024-05"))
                / "2024-05.pdf"
            )
            self.assertTrue(other_pdf.is_file())


class DeleteStatementsCliTests(unittest.TestCase):
    def test_parser_requires_identifier(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            _ = parser.parse_args([])


if __name__ == "__main__":
    _ = unittest.main()
