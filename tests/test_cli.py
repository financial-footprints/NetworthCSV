"""CLI library API tests."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from networthcsv.cli import apply_run_overrides, load_context
from networthcsv.errors import ConfigError
from networthcsv.settings import (
    RunSettings,
    accounts_to_run,
    load_settings,
    validate_run_filter,
)


class CliTests(unittest.TestCase):
    def _write_json(self, path: Path, data: object) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def _write_minimal_configs(self, root: Path) -> Path:
        user_config_path = root / "user.config.json"
        self._write_json(
            user_config_path,
            {
                "source": {"type": "thunderbird", "thunderbird": {"profile": "."}},
                "download_path": ".",
                "accounts": [
                    {
                        "bank": "bob",
                        "variant": "easy",
                        "account_number": "1",
                        "file_marker": "1",
                        "passwords": ["x"],
                    }
                ],
            },
        )
        app_config_path = root / "app.config.json"
        self._write_json(
            app_config_path,
            {
                "user_config": user_config_path.name,
                "banks": {
                    "bob": {
                        "default": {"subjects": ["stmt"]},
                        "easy": {"subjects": ["stmt"]},
                    }
                },
            },
        )
        return app_config_path

    def test_load_context_accepts_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            ctx = load_context(config_path=app_config_path)
            self.assertEqual(len(ctx.settings.accounts), 1)
            self.assertEqual(ctx.settings.accounts[0].bank, "bob")

    def test_apply_run_overrides_merges_run_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            settings = load_settings(app_config_path)
            updated = apply_run_overrides(settings, {"bank": "bob", "variant": "easy"})
            self.assertEqual(updated.run.bank, "bob")
            self.assertEqual(updated.run.variant, "easy")

    def test_load_context_applies_run_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            ctx = load_context(
                config_path=app_config_path,
                run_overrides=RunSettings(bank="bob", variant="easy"),
            )
            selected = accounts_to_run(ctx.settings)
            self.assertEqual(len(selected), 1)

    def test_apply_run_overrides_merges_account_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            settings = load_settings(app_config_path)
            updated = apply_run_overrides(
                settings, {"account_type": "credit_card", "bank": "bob"}
            )
            self.assertEqual(updated.run.account_type, "credit_card")
            self.assertEqual(updated.run.bank, "bob")

    def test_load_context_applies_account_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            ctx = load_context(
                config_path=app_config_path,
                run_overrides={"account_type": "credit_card", "bank": "bob"},
            )
            selected = accounts_to_run(ctx.settings)
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].account_type, "credit_card")

    def test_apply_run_overrides_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            with self.assertRaises(ValueError):
                _ = apply_run_overrides(
                    load_settings(app_config_path),
                    {"bank": "missing"},
                )

    def test_validate_run_filter_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            settings = load_settings(app_config_path)
            settings = dataclasses.replace(settings, run=RunSettings(bank="missing"))
            with self.assertRaises(ValueError):
                validate_run_filter(settings)

    def test_load_settings_raises_config_error_for_missing_file(self) -> None:
        with self.assertRaises(ConfigError):
            _ = load_settings("/tmp/does-not-exist-networthcsv-config.json")


if __name__ == "__main__":
    _ = unittest.main()
