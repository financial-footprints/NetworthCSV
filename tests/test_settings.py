"""Settings loading tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.settings import AccountSettings, Settings, find_account, load_settings, parser_bank


class SettingsTests(unittest.TestCase):
    def _write_config(self, directory: Path, data: dict[str, object]) -> Path:
        config_path = directory / "extractor.config.json"
        config_path.write_text(json.dumps(data), encoding="utf-8")
        return config_path

    def test_load_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            statements = root / "statements"
            statements.mkdir()
            profile = root / "profile"
            profile.mkdir()
            config_path = self._write_config(
                root,
                {
                    "profile": "profile",
                    "download_path": "statements",
                    "start_date": "2024-06-01",
                    "accounts": [
                        {
                            "bank": "bob",
                            "subjects": ["BOB CREDIT CARD"],
                            "passwords": ["secret", "secret", "other"],
                        }
                    ],
                },
            )
            settings = load_settings(config_path)
            self.assertEqual(settings.profile, profile.resolve())
            self.assertEqual(settings.download_path, statements.resolve())
            self.assertEqual(settings.start_date, date(2024, 6, 1))
            self.assertEqual(settings.accounts[0].bank, "bob")
            self.assertEqual(settings.accounts[0].subjects, ["BOB CREDIT CARD"])
            self.assertEqual(settings.accounts[0].passwords, ["secret", "other"])

    def test_legacy_subject_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(
                root,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [
                        {"bank": "bob", "subject": "BOB CREDIT CARD", "passwords": ["x"]},
                    ],
                },
            )
            settings = load_settings(config_path)
            self.assertEqual(settings.accounts[0].subjects, ["BOB CREDIT CARD"])

    def test_multiple_subjects(self) -> None:
        account = AccountSettings(
            bank="icici",
            subjects=[
                "Amazon Pay ICICI Bank Credit Card Statement for the period",
                "ICICI Bank Credit Card Statement for the period",
            ],
            passwords=["x"],
        )
        self.assertEqual(len(account.subjects), 2)

    def test_nested_bank_path(self) -> None:
        account = AccountSettings(
            bank="HDFC/Swiggy",
            subjects=["Swiggy statement"],
            passwords=["x"],
        )
        self.assertEqual(account.bank, "hdfc/swiggy")

    def test_parser_bank(self) -> None:
        account = AccountSettings(
            bank="hdfc/swiggy",
            subjects=["Swiggy statement"],
            passwords=["x"],
        )
        self.assertEqual(parser_bank(account), "hdfc")

    def test_missing_profile_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(
                root,
                {
                    "download_path": ".",
                    "accounts": [
                        {"bank": "bob", "subjects": ["BOB"], "passwords": ["x"]},
                    ],
                },
            )
            with self.assertRaises(SystemExit):
                load_settings(config_path)

    def test_password_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(
                root,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [
                        {"bank": "bob", "subjects": ["BOB"], "password": "legacy"},
                    ],
                },
            )
            with self.assertRaises(SystemExit):
                load_settings(config_path)

    def test_find_account(self) -> None:
        settings = Settings(
            profile=Path("/profile"),
            download_path=Path("/statements"),
            accounts=[AccountSettings(bank="bob", subjects=["BOB"], passwords=["x"])],
        )
        account = find_account(settings, Path("/statements/bob"))
        self.assertIsNotNone(account)
        assert account is not None
        self.assertEqual(account.bank, "bob")
        self.assertIsNone(find_account(settings, Path("/statements/missing")))

    def test_find_nested_account(self) -> None:
        settings = Settings(
            profile=Path("/profile"),
            download_path=Path("/statements"),
            accounts=[
                AccountSettings(
                    bank="hdfc/swiggy",
                    subjects=["Swiggy statement"],
                    passwords=["x"],
                )
            ],
        )
        account = find_account(settings, Path("/statements/hdfc/swiggy"))
        self.assertIsNotNone(account)
        assert account is not None
        self.assertEqual(account.bank, "hdfc/swiggy")


if __name__ == "__main__":
    unittest.main()
