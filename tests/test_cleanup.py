"""Cleanup pipeline tests."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.paths import statement_pdf_path, txt_path_for_pdf
from src.pipeline.cleanup.cleanup import collect_month_groups, prepare_month
from src.settings import ResolvedAccount


def _extract_side_effect(
    mapping: dict[Path, str],
) -> Callable[[Path, list[str]], str]:
    def side_effect(path: Path, _passwords: list[str]) -> str:
        return mapping[path]

    return side_effect


def _account(*, identifier: str = "5678") -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": "easy",
            "identifier": identifier,
            "subjects": ["BOB"],
            "bodies": [],
            "from": [],
            "passwords": ["secret"],
        }
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

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_writes_paired_pdf_and_txt_for_matching_staging_file(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            staging = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [staging],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertIn("5678", txt_out.read_text(encoding="utf-8"))
            self.assertFalse(staging.exists())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_keeps_last_matching_identifier_for_same_month(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            first = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(download_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "wrong card ending 1111",
                    second: "bob card ending 5678",
                }
            )

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [first, second],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            unknown_first = download_dir / "unknown" / first.name
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(first.exists())
            self.assertTrue(unknown_first.is_file())
            self.assertFalse(second.exists())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_strict_rejects_month_when_no_identifier_matches(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            first = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(download_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "wrong card ending 1111",
                    second: "also wrong card ending 2222",
                }
            )

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [first, second],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            unknown_dir = download_dir / "unknown"
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertTrue((unknown_dir / first.name).is_file())
            self.assertTrue((unknown_dir / second.name).is_file())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_reject_preserves_existing_month_outputs(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            staging = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            _ = pdf_out.parent.mkdir(parents=True, exist_ok=True)
            _ = pdf_out.write_bytes(b"%PDF-1.4")
            _ = txt_out.write_text("stale card ending 9999", encoding="utf-8")
            mock_extract.return_value = "wrong card ending 1111"

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [staging, pdf_out],
                _account(),
            )

            self.assertEqual((prepared, rejected), (0, 1))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())
            self.assertTrue((download_dir / "unknown" / staging.name).is_file())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_identifier_must_appear_in_sanitized_text(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            staging = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            mock_extract.return_value = "junk\n5678\n********** End of Statement **********"

            account = _account()
            account = account.model_copy(update={"end_marker": "End of Statement"})

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [staging],
                account,
            )

            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertIn("5678", txt_out.read_text(encoding="utf-8"))

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_keeps_last_when_both_match_identifier(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            first = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            second = self._write_pdf(download_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    first: "bob card ending 5678",
                    second: "bob card ending 5678 duplicate",
                }
            )

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [first, second],
                _account(),
            )

            txt_out = txt_path_for_pdf(download_dir, statement_pdf_path(download_dir, "2023-04"))
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(statement_pdf_path(download_dir, "2023-04").is_file())
            self.assertIn("duplicate", txt_out.read_text(encoding="utf-8"))
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_hash_dedupe_staging_siblings_all_removed(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            payload = b"%PDF-1.4\nidentical-statement-bytes"
            bob = self._write_identical_pdf(
                download_dir, "BOB (Easy Shopping)__2024-04-17.pdf", payload
            )
            inbox = self._write_identical_pdf(
                download_dir, "INBOX__2024-04-17.pdf", payload
            )
            starred = self._write_identical_pdf(
                download_dir, "Starred__2024-04-17.pdf", payload
            )
            important = self._write_identical_pdf(
                download_dir, "Important__2024-04-17.pdf", payload
            )
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                download_dir,
                "2024-04",
                [bob, inbox, starred, important],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2024-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(bob.exists())
            self.assertFalse(inbox.exists())
            self.assertFalse(starred.exists())
            self.assertFalse(important.exists())

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_reject_quarantines_all_staging_duplicates_for_month(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            payload = b"%PDF-1.4\nidentical-statement-bytes"
            first = self._write_identical_pdf(
                download_dir, "All Mail__2023-04-18.pdf", payload
            )
            second = self._write_identical_pdf(
                download_dir, "Starred__2023-04-18.pdf", payload
            )
            third = self._write_identical_pdf(
                download_dir, "INBOX__2023-04-18.pdf", payload
            )
            mock_extract.return_value = "wrong card ending 1111"

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [first, second, third],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2023-04")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            unknown_dir = download_dir / "unknown"
            self.assertEqual((prepared, rejected), (0, 1))
            self.assertFalse(pdf_out.is_file())
            self.assertFalse(txt_out.is_file())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse(third.exists())
            self.assertEqual(len(list(unknown_dir.glob("*.pdf"))), 1)

    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_writes_paired_outputs_for_uppercase_pdf_extension(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            staging = self._write_pdf(download_dir, "All Mail__2024-01-21.PDF")
            mock_extract.return_value = "bob card ending 5678"

            prepared, rejected = prepare_month(
                download_dir,
                "2024-01",
                [staging],
                _account(),
            )

            pdf_out = statement_pdf_path(download_dir, "2024-01")
            txt_out = txt_path_for_pdf(download_dir, pdf_out)
            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue(pdf_out.is_file())
            self.assertTrue(txt_out.is_file())
            self.assertFalse(staging.exists())


    @patch("src.pipeline.cleanup.cleanup.extract_pdf_text_plumber")
    def test_moves_wrong_identifier_sibling_to_unknown(
        self, mock_extract: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            wrong = self._write_pdf(download_dir, "All Mail__2023-04-18.pdf")
            right = self._write_pdf(download_dir, "Starred_Email__2023-04-18.pdf")
            mock_extract.side_effect = _extract_side_effect(
                {
                    wrong: "wrong card ending 1111",
                    right: "bob card ending 5678",
                }
            )

            prepared, rejected = prepare_month(
                download_dir,
                "2023-04",
                [wrong, right],
                _account(),
            )

            self.assertEqual((prepared, rejected), (1, 0))
            self.assertTrue((download_dir / "unknown" / wrong.name).is_file())
            self.assertFalse(wrong.exists())
            self.assertFalse(right.exists())


class CollectMonthGroupsTests(unittest.TestCase):
    def test_groups_uppercase_staging_pdfs_by_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            first = download_dir / "All Mail__2024-01-21.PDF"
            second = download_dir / "INBOX__2024-01-21.PDF"
            _ = first.write_bytes(b"%PDF-1.4\nfirst")
            _ = second.write_bytes(b"%PDF-1.4\nsecond")

            groups = collect_month_groups(download_dir)

            self.assertEqual(list(groups.keys()), ["2024-01"])
            self.assertEqual(sorted(path.name for path in groups["2024-01"]), sorted(
                [first.name, second.name]
            ))


if __name__ == "__main__":
    _ = unittest.main()
