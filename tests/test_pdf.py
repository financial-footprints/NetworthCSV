"""PDF encryption and text extraction tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from networthcsv.errors import StageError
from networthcsv.pipeline.cleanup.cleanup import decrypt_pdfs_in_place
from networthcsv.utils.pdf import extract_pdf_text_plumber, pdf_is_encrypted


def _write_unencrypted_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        _ = writer.write(handle)


def _write_encrypted_pdf(path: Path, *, user_password: str) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password=user_password)
    with path.open("wb") as handle:
        _ = writer.write(handle)


def _write_owner_only_encrypted_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="", owner_password="owner")
    with path.open("wb") as handle:
        _ = writer.write(handle)


class PdfIsEncryptedTests(unittest.TestCase):
    def test_unencrypted_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.pdf"
            _write_unencrypted_pdf(path)
            self.assertFalse(pdf_is_encrypted(path))

    def test_encrypted_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.pdf"
            _write_encrypted_pdf(path, user_password="secret")
            self.assertTrue(pdf_is_encrypted(path))


class ExtractPdfTextPlumberTests(unittest.TestCase):
    def test_unencrypted_pdf_opens_without_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.pdf"
            _write_unencrypted_pdf(path)
            result = extract_pdf_text_plumber(path, ["wrong-password"])
            self.assertIsInstance(result, str)

    def test_unencrypted_pdf_does_not_try_account_passwords(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.pdf"
            _write_unencrypted_pdf(path)
            calls: list[dict[str, object]] = []

            original_open = __import__("pdfplumber").open

            def spy_open(path_str: str, **kwargs: object):
                calls.append(kwargs)
                return original_open(path_str, **kwargs)

            with patch("networthcsv.utils.pdf.pdfplumber.open", side_effect=spy_open):
                _ = extract_pdf_text_plumber(path, ["wrong-password"])

            self.assertEqual(len(calls), 1)
            self.assertNotIn("password", calls[0])

    def test_encrypted_pdf_succeeds_with_correct_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.pdf"
            _write_encrypted_pdf(path, user_password="secret")
            result = extract_pdf_text_plumber(path, ["wrong-password", "secret"])
            self.assertIsInstance(result, str)

    def test_corrupt_unencrypted_pdf_raises_without_password_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.pdf"
            _ = path.write_bytes(b"%PDF-1.4 not-a-valid-pdf")
            password_attempts: list[str] = []

            def spy_open(path_str: str, password: str | None = None):
                if password is not None:
                    password_attempts.append(password)
                raise PdfReadError("corrupt")

            with patch("networthcsv.utils.pdf.pdfplumber.open", side_effect=spy_open):
                with self.assertRaises(StageError):
                    _ = extract_pdf_text_plumber(path, ["secret"])

            self.assertEqual(password_attempts, [])


class DecryptPdfsInPlaceTests(unittest.TestCase):
    def test_skips_unencrypted_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            path = staging / "plain.pdf"
            _write_unencrypted_pdf(path)
            original = path.read_bytes()

            decrypted = decrypt_pdfs_in_place(staging, ["secret"])

            self.assertEqual(decrypted, 0)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(pdf_is_encrypted(path))

    def test_decrypts_owner_only_pdf_with_empty_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            path = staging / "owner-locked.pdf"
            _write_owner_only_encrypted_pdf(path)
            self.assertTrue(pdf_is_encrypted(path))

            decrypted = decrypt_pdfs_in_place(staging, ["account-password"])

            self.assertEqual(decrypted, 1)
            self.assertFalse(pdf_is_encrypted(path))
            reader = PdfReader(str(path))
            self.assertGreater(len(reader.pages), 0)

    def test_decrypts_user_password_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            path = staging / "user-locked.pdf"
            _write_encrypted_pdf(path, user_password="secret")
            self.assertTrue(pdf_is_encrypted(path))

            decrypted = decrypt_pdfs_in_place(staging, ["wrong", "secret"])

            self.assertEqual(decrypted, 1)
            self.assertFalse(pdf_is_encrypted(path))

    def test_raises_when_no_password_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            path = staging / "locked.pdf"
            _write_encrypted_pdf(path, user_password="secret")

            with self.assertRaises(StageError):
                _ = decrypt_pdfs_in_place(staging, ["wrong-password"])

            self.assertTrue(pdf_is_encrypted(path))


if __name__ == "__main__":
    _ = unittest.main()
