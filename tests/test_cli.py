"""CLI library API tests."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from networthcsv.cli import (
    apply_run_overrides,
    load_context,
    parse_run_args,
)
from networthcsv.errors import ConfigError
from networthcsv.settings import AppSettings, RunSettings
from helpers import test_env, write_accounts


class CliTests(unittest.TestCase):
    def _write_minimal_configs(self, root: Path) -> Path:
        return write_accounts(
            root,
            [
                {
                    "bank": "bob",
                    "variant": "easy",
                    "account_number": "1",
                    "statement": {"text_contains": "1"},
                    "passwords": ["x"],
                    "opening_date": "01-01-2020",
                }
            ],
        )

    def test_load_context_accepts_preloaded_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root):
                settings = AppSettings.from_user_accounts(
                    [
                        {
                            "bank": "bob",
                            "variant": "easy",
                            "account_number": "1",
                            "statement": {"text_contains": ["1"]},
                            "passwords": ["x"],
                            "opening_date": "01-01-2020",
                        }
                    ],
                )
                ctx = load_context(settings=settings)
            self.assertEqual(len(ctx.settings.accounts), 1)
            self.assertEqual(ctx.settings.accounts[0].bank, "bob")

    def test_load_context_accepts_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = self._write_minimal_configs(root)
            with test_env(root):
                ctx = load_context(config_path=accounts_path)
            self.assertEqual(len(ctx.settings.accounts), 1)
            self.assertEqual(ctx.settings.accounts[0].bank, "bob")

    def test_apply_run_overrides_merges_run_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = self._write_minimal_configs(root)
            with test_env(root):
                settings = AppSettings.load(accounts_path)
            updated = apply_run_overrides(settings, {"identifier": "1"})
            self.assertEqual(updated.run.identifier, "1")

    def test_load_context_applies_run_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = self._write_minimal_configs(root)
            with test_env(root):
                ctx = load_context(
                    config_path=accounts_path,
                    run_overrides=RunSettings(identifier="1"),
                )
            selected = ctx.settings.accounts_to_run()
            self.assertEqual(len(selected), 1)

    def test_parse_run_args_reads_identifier(self) -> None:
        options = parse_run_args(["--identifier", "abcd"])
        self.assertIsNotNone(options.run_overrides)
        assert options.run_overrides is not None
        self.assertEqual(options.run_overrides.identifier, "abcd")

    def test_parse_run_args_reads_short_identifier_flag(self) -> None:
        options = parse_run_args(["-i", "abcd"])
        self.assertIsNotNone(options.run_overrides)
        assert options.run_overrides is not None
        self.assertEqual(options.run_overrides.identifier, "abcd")

    def test_parse_run_args_reads_config_path(self) -> None:
        options = parse_run_args(["--config", "/tmp/accounts.json"])
        self.assertEqual(options.config_path, Path("/tmp/accounts.json"))

    def test_apply_run_overrides_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = self._write_minimal_configs(root)
            with test_env(root):
                settings = AppSettings.load(accounts_path)
            with self.assertRaises(ValueError):
                _ = apply_run_overrides(
                    settings,
                    {"identifier": "missing"},
                )

    def test_validate_run_filter_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = self._write_minimal_configs(root)
            with test_env(root):
                settings = AppSettings.load(accounts_path)
            settings = dataclasses.replace(
                settings, run=RunSettings(identifier="missing")
            )
            with self.assertRaises(ValueError):
                settings.validate_run_filter()

    def test_load_settings_raises_config_error_for_missing_file(self) -> None:
        with self.assertRaises(ConfigError):
            _ = AppSettings.load("/tmp/does-not-exist-networthcsv-config.json")


if __name__ == "__main__":
    _ = unittest.main()
