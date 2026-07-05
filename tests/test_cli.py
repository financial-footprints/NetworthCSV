"""CLI library API tests."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from networthcsv.cli import (
    apply_run_overrides,
    load_context,
    parse_run_args,
)
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
                        "file_markers": "1",
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
            updated = apply_run_overrides(settings, {"identifier": "1"})
            self.assertEqual(updated.run.identifier, "1")

    def test_load_context_applies_run_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            ctx = load_context(
                config_path=app_config_path,
                run_overrides=RunSettings(identifier="1"),
            )
            selected = accounts_to_run(ctx.settings)
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
        options = parse_run_args(["--config", "/tmp/app.config.json"])
        self.assertEqual(options.config_path, Path("/tmp/app.config.json"))

    def test_apply_run_overrides_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            with self.assertRaises(ValueError):
                _ = apply_run_overrides(
                    load_settings(app_config_path),
                    {"identifier": "missing"},
                )

    def test_validate_run_filter_raises_when_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_config_path = self._write_minimal_configs(Path(tmp))
            settings = load_settings(app_config_path)
            settings = dataclasses.replace(
                settings, run=RunSettings(identifier="missing")
            )
            with self.assertRaises(ValueError):
                validate_run_filter(settings)

    def test_load_settings_raises_config_error_for_missing_file(self) -> None:
        with self.assertRaises(ConfigError):
            _ = load_settings("/tmp/does-not-exist-networthcsv-config.json")


if __name__ == "__main__":
    _ = unittest.main()
