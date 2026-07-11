"""Cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from networthcsv.utils.path import statement_pdf_path, txt_path_for_pdf
from networthcsv.context import RunContext
from networthcsv.pipeline.cleanup.cleanup import (
    collect_month_groups,
    prepare_month,
    run,
)
from networthcsv.pipeline.reporter import NullRunReporter
from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks import get_handler


def _extract_side_effect(
    mapping: dict[Path, str],
) -> Callable[[Path, list[str]], str]:
    def side_effect(path: Path, _passwords: list[str]) -> str:
        return mapping[path]

    return side_effect


def _account(
    *,
    bank: str = "bob",
    variant: str | None = "easy",
    text_contains: list[str] | str = "5678",
    account_number: str = "5678",
) -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
    statement_text_contains = (
        text_contains if isinstance(text_contains, list) else [text_contains]
    )
    payload = defaults.model_dump()
    payload["statement"] = {
        **payload["statement"],
        "text_contains": statement_text_contains,
    }
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": account_number,
            "passwords": ["secret"],
            **payload,
        }
    )


def _staging_layout(
    tmp: str, account: ResolvedAccount | None = None
) -> tuple[Path, Path, ResolvedAccount]:
    download_path = Path(tmp)
    resolved = account or _account()
    staging_dir = download_path / "credit_card" / resolved.account_number
    _ = staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir, download_path, resolved


def _run_context(download_path: Path) -> RunContext:
    return RunContext(
        settings=Settings(
            source=ThunderbirdSource(
                thunderbird=ThunderbirdSourceSettings(profile=Path("."))
            ),
            download_path=download_path,
            accounts=[],
            alerts=None,
            run=RunSettings(),
        ),
        alerts=AlertService(handler=None),
        reporter=NullRunReporter(),
    )


class PrepareMonthTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    def _write_identical_pdf(self, directory: Path, name: str, payload: bytes) -> Path:
        path = directory / name
        _ = path.write_bytes(payload)
        return path

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_accepts_month_when_text_contains_blank(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            account = _account(text_contains=[], account_number="acct-1")
            staging_dir, download_path, account = _staging_layout(tmp, account)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "statement with no matchable marker"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_writes_paired_pdf_and_txt_for_matching_staging_file(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertIn("5678", txt_out.read_text(encoding="utf-8"))
            self.assertFalse(staging.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_prepare_month_accepts_manual_upload_without_text_contains_in_text(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            staging = self._write_pdf(staging_dir, "manual__2023-05.pdf")
            mock_extract.return_value = "generic statement text with no account marker"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-05",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-05")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_keeps_last_matching_identifier_for_same_month(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            first = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(staging_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "wrong card ending 1111",
                    second: "bob card ending 5678",
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [first, second],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertTrue(first.is_file())
            self.assertFalse(second.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_strict_rejects_month_when_no_identifier_matches(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            first = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(staging_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "wrong card ending 1111",
                    second: "also wrong card ending 2222",
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [first, second],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_accepts_month_when_any_text_contains_matches(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            account = _account(
                text_contains=["5678", "XXXX5678"], account_number="5678"
            )
            staging_dir, download_path, account = _staging_layout(tmp, account)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "card ending XXXX5678"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertIn("XXXX5678", txt_out.read_text(encoding="utf-8"))

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_rejects_month_when_no_text_contains_match(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            account = _account(
                text_contains=["5678", "XXXX5678"], account_number="5678"
            )
            staging_dir, download_path, account = _staging_layout(tmp, account)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "card ending 9999"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertTrue(staging.is_file())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_reject_preserves_existing_month_outputs(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            _ = pdf_out.parent.mkdir(parents=True, exist_ok=True)
            _ = pdf_out.write_bytes(b"%PDF-1.4")
            _ = txt_out.write_text("stale card ending 9999", encoding="utf-8")
            mock_extract.return_value = "wrong card ending 1111"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging, pdf_out],
                account,
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertTrue(staging.is_file())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_identifier_must_appear_in_sanitized_text(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            account = _account(bank="pnb", variant=None)
            staging_dir, download_path, account = _staging_layout(tmp, account)
            staging = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = (
                "junk\n5678\n********** End of Statement **********"
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertIn("5678", txt_out.read_text(encoding="utf-8"))

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_keeps_last_when_both_match_identifier(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            first = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(staging_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "bob card ending 5678",
                    second: "bob card ending 5678 duplicate",
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [first, second],
                account,
            )

            txt_out = txt_path_for_pdf(
                statement_pdf_path(download_path, account, "2023-04")
            )
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(
                statement_pdf_path(download_path, account, "2023-04").is_file()
            )
            self.assertIn("duplicate", txt_out.read_text(encoding="utf-8"))
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_hash_dedupe_staging_siblings_all_removed(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            payload = b"%PDF-1.4\nidentical-statement-bytes"
            bob = self._write_identical_pdf(
                staging_dir, "BOB (Easy Shopping)__2024-04-17.pdf", payload
            )
            inbox = self._write_identical_pdf(
                staging_dir, "INBOX__2024-04-17.pdf", payload
            )
            starred = self._write_identical_pdf(
                staging_dir, "Starred__2024-04-17.pdf", payload
            )
            important = self._write_identical_pdf(
                staging_dir, "Important__2024-04-17.pdf", payload
            )
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-04",
                [bob, inbox, starred, important],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2024-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(bob.exists())
            self.assertFalse(inbox.exists())
            self.assertFalse(starred.exists())
            self.assertFalse(important.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_reject_leaves_staging_duplicates_in_place(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            payload = b"%PDF-1.4\nidentical-statement-bytes"
            first = self._write_identical_pdf(
                staging_dir, "All Mail__2023-04-18.pdf", payload
            )
            second = self._write_identical_pdf(
                staging_dir, "Starred__2023-04-18.pdf", payload
            )
            third = self._write_identical_pdf(
                staging_dir, "INBOX__2023-04-18.pdf", payload
            )
            mock_extract.return_value = "wrong card ending 1111"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [first, second, third],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2023-04")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertTrue(third.is_file())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_writes_paired_outputs_for_uppercase_pdf_extension(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            staging = self._write_pdf(staging_dir, "All Mail__2024-01-21.PDF")
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2024-01",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_path, account, "2024-01")
            txt_out = txt_path_for_pdf(pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_leaves_wrong_identifier_sibling_in_staging(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            wrong = self._write_pdf(staging_dir, "All Mail__2023-04-18.pdf")
            right = self._write_pdf(staging_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    wrong: "wrong card ending 1111",
                    right: "bob card ending 5678",
                }
            )

            prepared, rejected = prepare_month(
                staging_dir,
                download_path,
                "2023-04",
                [wrong, right],
                account,
            )

            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(wrong.is_file())
            self.assertFalse(right.exists())


class CollectMonthGroupsTests(unittest.TestCase):
    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_groups_uppercase_staging_pdfs_by_filename_fallback(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, _download_path, account = _staging_layout(tmp)
            first = staging_dir / "All Mail__2024-01-21.PDF"
            second = staging_dir / "INBOX__2024-01-21.PDF"
            _ = first.write_bytes(b"%PDF-1.4\nfirst")
            _ = second.write_bytes(b"%PDF-1.4\nsecond")
            mock_extract.return_value = "no statement date in text"

            collected = collect_month_groups(staging_dir, account)

            self.assertEqual(list(collected.groups.keys()), ["2024-01"])
            self.assertEqual(
                sorted(path.name for path in collected.groups["2024-01"]),
                sorted([first.name, second.name]),
            )

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_groups_by_statement_date_not_email_filename(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, _download_path, account = _staging_layout(tmp)
            staging = staging_dir / "All Mail__2023-05-20.pdf"
            _ = staging.write_bytes(b"%PDF-1.4\nbob")
            mock_extract.return_value = (
                "Credit Card Monthly Statement\n"
                "Statement Date : 16/04/2023 | Statement Period : 17 Mar, 2023 to 16 Apr, 2023\n"
                "bob card ending 5678"
            )

            collected = collect_month_groups(staging_dir, account)

            self.assertEqual(list(collected.groups.keys()), ["2023-04"])
            self.assertEqual(collected.groups["2023-04"], [staging])
            self.assertEqual(collected.path_month[staging], "2023-04")

    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_manual_upload_uses_filename_month_over_pdf_text(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, _download_path, account = _staging_layout(tmp)
            manual = staging_dir / "manual__2024-02.pdf"
            _ = manual.write_bytes(b"%PDF-1.4\nbob")
            mock_extract.return_value = (
                "Credit Card Monthly Statement\n"
                "Statement Date : 16/04/2023 | Statement Period : 17 Mar, 2023 to 16 Apr, 2023\n"
                "bob card ending 5678"
            )

            collected = collect_month_groups(staging_dir, account)

            self.assertEqual(list(collected.groups.keys()), ["2024-02"])
            self.assertEqual(collected.groups["2024-02"], [manual])
            self.assertEqual(collected.path_month[manual], "2024-02")


class RunCleanupTests(unittest.TestCase):
    def _write_pdf(self, directory: Path, name: str) -> Path:
        path = directory / name
        _ = path.write_bytes(b"%PDF-1.4\n" + name.encode("utf-8"))
        return path

    @patch("networthcsv.pipeline.cleanup.cleanup.decrypt_pdfs_in_place", return_value=0)
    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_run_skips_unknown_month_leaving_files_in_staging(
        self, mock_extract: MagicMock, _mock_decrypt: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            staging = self._write_pdf(staging_dir, "attachment.pdf")
            mock_extract.return_value = "no parseable statement date"

            result = run(staging_dir, account, _run_context(download_path))

            unknown_out = statement_pdf_path(download_path, account, "unknown-month")
            self.assertTrue(staging.is_file())
            self.assertFalse(unknown_out.is_file())
            self.assertEqual(result.prepared, 0)
            self.assertEqual(result.rejected, 0)

    @patch("networthcsv.pipeline.cleanup.cleanup.decrypt_pdfs_in_place", return_value=0)
    @patch("networthcsv.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_run_upload_scope_processes_only_manual_pdf(
        self, mock_extract: MagicMock, _mock_decrypt: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging_dir, download_path, account = _staging_layout(tmp)
            manual = self._write_pdf(staging_dir, "manual__2024-02.pdf")
            other = self._write_pdf(staging_dir, "INBOX__2024-01-21.pdf")
            mock_extract.return_value = "generic statement text with no account marker"

            result = run(
                staging_dir,
                account,
                _run_context(download_path),
                upload_statement_date="2024-02",
            )

            pdf_out = statement_pdf_path(download_path, account, "2024-02")
            self.assertTrue(pdf_out.is_file())
            self.assertFalse(manual.exists())
            self.assertTrue(other.is_file())
            self.assertEqual(result.prepared, 1)
            self.assertEqual(result.rejected, 0)


if __name__ == "__main__":
    _ = unittest.main()
