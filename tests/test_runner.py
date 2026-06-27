"""Pipeline runner and runtime API tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from networthcsv.context import RunContext
from networthcsv.errors import StageError
from networthcsv.pipeline.cleanup.cleanup import run as cleanup_run
from networthcsv.pipeline.parse.parse import run as parse_run
from networthcsv.pipeline.reporter import NullRunReporter
from networthcsv.pipeline.results import (
    CleanupAccountResult,
    ExtractAccountResult,
    ExtractStageResult,
    MetadataAccountResult,
    ParseAccountResult,
    PipelineResult,
)
from networthcsv.pipeline.runner import (
    run_cleanup,
    run_extract,
    run_metadata,
    run_parse,
    run_pipeline,
)
from networthcsv.runtime import process
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.path import discover_account_fy_dirs
from networthcsv.settings import ResolvedAccount, load_settings


def _write_minimal_configs(root: Path) -> Path:
    user_config_path = root / "user.config.json"
    user_config_path.write_text(
        json.dumps(
            {
                "source": {"type": "thunderbird", "thunderbird": {"profile": "."}},
                "download_path": str(root / "downloads"),
                "accounts": [
                    {
                        "bank": "bob",
                        "variant": "easy",
                        "account_number": "1",
                        "file_marker": "1",
                        "passwords": ["x"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app_config_path = root / "app.config.json"
    app_config_path.write_text(
        json.dumps(
            {
                "user_config": user_config_path.name,
                "banks": {
                    "bob": {
                        "default": {"subjects": ["stmt"]},
                        "easy": {"subjects": ["stmt"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return app_config_path


def _write_two_account_configs(root: Path) -> Path:
    user_config_path = root / "user.config.json"
    user_config_path.write_text(
        json.dumps(
            {
                "source": {"type": "thunderbird", "thunderbird": {"profile": "."}},
                "download_path": str(root / "downloads"),
                "accounts": [
                    {
                        "bank": "bob",
                        "variant": "easy",
                        "account_number": "1",
                        "file_marker": "1",
                        "passwords": ["x"],
                    },
                    {
                        "bank": "bob",
                        "variant": "other",
                        "account_number": "2",
                        "file_marker": "2",
                        "passwords": ["x"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    app_config_path = root / "app.config.json"
    app_config_path.write_text(
        json.dumps(
            {
                "user_config": user_config_path.name,
                "banks": {
                    "bob": {
                        "default": {"subjects": ["stmt"]},
                        "easy": {"subjects": ["stmt"]},
                        "other": {"subjects": ["stmt"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return app_config_path


def _context(root: Path) -> RunContext:
    settings = load_settings(_write_minimal_configs(root))
    return RunContext(settings=settings, alerts=AlertService(handler=None))


class RunnerTests(unittest.TestCase):
    @patch("networthcsv.pipeline.runner.extract_stage.run_all")
    def test_run_extract_delegates_to_extract_stage(
        self, mock_run_all: MagicMock
    ) -> None:
        expected = ExtractStageResult(accounts=())
        mock_run_all.return_value = expected
        with tempfile.TemporaryDirectory() as tmp:
            result = run_extract(_context(Path(tmp)))
        self.assertIs(result, expected)

    @patch("networthcsv.pipeline.runner.cleanup_stage.run_account")
    def test_run_cleanup_runs_each_account(self, mock_run_account: MagicMock) -> None:
        mock_run_account.return_value = CleanupAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            non_pdf_removed=0,
            decrypted=0,
            prepared=0,
            rejected=0,
            orphans_removed=0,
            legacy_folders_removed=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            results = run_cleanup(_context(Path(tmp)))
        self.assertEqual(len(results), 1)
        mock_run_account.assert_called_once()

    @patch("networthcsv.pipeline.runner.parse_stage.run_account")
    def test_run_parse_runs_each_account(self, mock_run_account: MagicMock) -> None:
        mock_run_account.return_value = ParseAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            fy_results=(),
            total_transactions=0,
            total_txts=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            results = run_parse(_context(Path(tmp)))
        self.assertEqual(len(results), 1)

    @patch("networthcsv.pipeline.runner.metadata_stage.run_account")
    def test_run_metadata_runs_each_account(self, mock_run_account: MagicMock) -> None:
        mock_run_account.return_value = MetadataAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            output=Path("/tmp/credit_card/1/metadata.json"),
            statement_count=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            results = run_metadata(_context(Path(tmp)))
        self.assertEqual(len(results), 1)
        mock_run_account.assert_called_once()

    @patch("networthcsv.pipeline.runner.parse_stage.run_account")
    @patch("networthcsv.pipeline.runner.metadata_stage.run_account")
    @patch("networthcsv.pipeline.runner.cleanup_stage.run_account")
    @patch("networthcsv.pipeline.runner.extract_stage.run_all")
    def test_run_pipeline_sequences_stages(
        self,
        mock_extract: MagicMock,
        mock_cleanup: MagicMock,
        mock_metadata: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        mock_extract.return_value = ExtractStageResult(
            accounts=(
                ExtractAccountResult(
                    bank="bob",
                    download_dir=Path("/tmp"),
                    messages_matched=0,
                    attachments_saved=0,
                ),
            )
        )
        mock_cleanup.return_value = CleanupAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            non_pdf_removed=0,
            decrypted=0,
            prepared=0,
            rejected=0,
            orphans_removed=0,
            legacy_folders_removed=0,
        )
        mock_metadata.return_value = MetadataAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            output=Path("/tmp/credit_card/1/metadata.json"),
            statement_count=0,
        )
        mock_parse.return_value = ParseAccountResult(
            bank="bob",
            download_dir=Path("/tmp"),
            fy_results=(),
            total_transactions=0,
            total_txts=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_pipeline(_context(Path(tmp)))
        self.assertEqual(len(result.extract.accounts), 1)
        self.assertEqual(len(result.cleanup), 1)
        self.assertEqual(len(result.metadata), 1)
        self.assertEqual(len(result.parse), 1)


class RuntimeApiTests(unittest.TestCase):
    @patch("networthcsv.runtime.run_pipeline")
    def test_process_returns_pipeline_result(
        self, mock_run_pipeline: MagicMock
    ) -> None:
        expected = PipelineResult(
            extract=ExtractStageResult(accounts=()),
            cleanup=(),
            metadata=(),
            parse=(),
        )
        mock_run_pipeline.return_value = expected
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext(
                settings=load_settings(_write_minimal_configs(Path(tmp))),
                alerts=AlertService(handler=None),
                reporter=NullRunReporter(),
            )
            self.assertIs(process(ctx), expected)


class StageErrorTests(unittest.TestCase):
    def test_parse_returns_empty_when_no_fy_dirs(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1",
                "file_marker": "1",
                "subjects": ["stmt"],
                "passwords": ["x"],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext(
                settings=load_settings(_write_minimal_configs(Path(tmp))),
                alerts=AlertService(handler=None),
                reporter=NullRunReporter(),
            )
            result = parse_run(account, ctx)
        self.assertFalse(result.skipped)
        self.assertEqual(result.total_transactions, 0)

    def test_cleanup_skips_missing_directory(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1",
                "file_marker": "1",
                "subjects": ["stmt"],
                "passwords": ["x"],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext(
                settings=load_settings(_write_minimal_configs(Path(tmp))),
                alerts=AlertService(handler=None),
                reporter=NullRunReporter(),
            )
            missing = Path(tmp) / "missing"
            result = cleanup_run(missing, account, ctx)
        self.assertTrue(result.skipped)
        self.assertEqual(result.prepared, 0)

    def test_run_cleanup_continues_when_one_account_directory_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_two_account_configs(root)
            settings = load_settings(root / "app.config.json")
            ctx = RunContext(
                settings=settings,
                alerts=AlertService(handler=None),
                reporter=NullRunReporter(),
            )
            present = settings.download_path / "credit_card" / "1"
            _ = present.mkdir(parents=True)

            results = run_cleanup(ctx)

        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].skipped)
        self.assertTrue(results[1].skipped)

    def test_discover_account_fy_dirs_raises_stage_error_for_missing_limit(
        self,
    ) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1",
                "file_marker": "1",
                "subjects": ["stmt"],
                "passwords": ["x"],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            limit = root / "FY99-9999" / "credit_card" / "1"
            with self.assertRaises(StageError):
                _ = discover_account_fy_dirs(root, account, limit)


if __name__ == "__main__":
    _ = unittest.main()
