"""ZIP archive extraction tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from networthcsv.utils.zip_archive import (
    ExtractedCsv,
    ZipArchiveError,
    ZipNoCsvError,
    ZipPasswordError,
    extract_csvs_from_zip,
    sanitize_zip_member_name,
)
from helpers import build_aes_zip, build_zip


class ZipArchiveTests(unittest.TestCase):
    def test_extract_single_csv(self) -> None:
        data = build_zip({"statement.csv": b"Date,Amount\n2024-01-01,1.00\n"})
        extracted = extract_csvs_from_zip(data, [])
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].inner_name, "statement.csv")
        self.assertIn(b"Date,Amount", extracted[0].content)

    def test_extract_multiple_csvs(self) -> None:
        data = build_zip(
            {
                "folder/a.csv": b"a",
                "folder/b.CSV": b"b",
            }
        )
        extracted = extract_csvs_from_zip(data, [])
        self.assertEqual(len(extracted), 2)
        names = {item.inner_name for item in extracted}
        self.assertEqual(names, {"a.csv", "b.CSV"})

    def test_skips_non_csv_and_macosx(self) -> None:
        data = build_zip(
            {
                "__MACOSX/._statement.csv": b"meta",
                "readme.txt": b"ignore",
                "statement.csv": b"data",
            }
        )
        extracted = extract_csvs_from_zip(data, [])
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].inner_name, "statement.csv")

    def test_rejects_zip_slip_member(self) -> None:
        data = build_zip({"../escape.csv": b"bad"})
        with self.assertRaises(ZipNoCsvError):
            _ = extract_csvs_from_zip(data, [])

    def test_no_csv_members_raises(self) -> None:
        data = build_zip({"readme.txt": b"no csv here"})
        with self.assertRaises(ZipNoCsvError):
            _ = extract_csvs_from_zip(data, [])

    def test_invalid_zip_raises(self) -> None:
        with self.assertRaises(ZipArchiveError):
            _ = extract_csvs_from_zip(b"not-a-zip", [])

    def test_tries_passwords_in_order(self) -> None:
        passwords_tried: list[str] = []

        def fake_extract(data: bytes, password: str) -> list[ExtractedCsv]:
            passwords_tried.append(password)
            if password != "right":
                raise RuntimeError("bad password")
            return [ExtractedCsv("statement.csv", b"ok")]

        with patch(
            "networthcsv.utils.zip_archive._extract_csv_members",
            side_effect=fake_extract,
        ):
            extracted = extract_csvs_from_zip(b"zip-bytes", ["wrong", "right"])

        self.assertEqual(passwords_tried, ["", "wrong", "right"])
        self.assertEqual(extracted[0].content, b"ok")

    def test_password_failure_raises(self) -> None:
        def always_fail(data: bytes, password: str) -> list[ExtractedCsv]:
            raise RuntimeError("bad password")

        with patch(
            "networthcsv.utils.zip_archive._extract_csv_members",
            side_effect=always_fail,
        ):
            with self.assertRaises(ZipPasswordError) as ctx:
                _ = extract_csvs_from_zip(b"zip-bytes", ["one", "two"])

        self.assertIn("configured password(s)", str(ctx.exception))
        self.assertIn("empty password", str(ctx.exception))

    def test_extract_aes_encrypted_csv(self) -> None:
        data = build_aes_zip(
            {"statement.csv": b"Date,Amount\n2024-01-01,1.00\n"},
            "secret",
        )
        extracted = extract_csvs_from_zip(data, ["secret"])
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].inner_name, "statement.csv")
        self.assertIn(b"Date,Amount", extracted[0].content)

    def test_aes_password_failure_raises(self) -> None:
        data = build_aes_zip({"statement.csv": b"data"}, "secret")
        with self.assertRaises(ZipPasswordError) as ctx:
            _ = extract_csvs_from_zip(data, ["wrong"])
        self.assertIn("configured password(s)", str(ctx.exception))

    def test_sanitize_zip_member_name(self) -> None:
        self.assertEqual(sanitize_zip_member_name("nested/path/file.csv"), "file.csv")
        self.assertEqual(sanitize_zip_member_name("../bad.csv"), "bad.csv")


if __name__ == "__main__":
    _ = unittest.main()
