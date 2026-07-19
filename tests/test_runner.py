"""Pipeline runner and runtime API tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from networthcsv.context import RunContext
from networthcsv.errors import JobCancelledError, StageError
from networthcsv.pipeline.cleanup import run as cleanup_run
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
from networthcsv.runtime import process, process_upload
from networthcsv.settings import AppSettings, ResolvedAccount
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.path import discover_account_fy_dirs
from helpers import default_test_env, write_accounts


def _write_minimal_configs(root: Path) -> Path:
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


def _write_two_account_configs(root: Path) -> Path:
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
            },
            {
                "bank": "bob",
                "variant": "default",
                "account_number": "2",
                "statement": {"text_contains": "2"},
                "passwords": ["x"],
                "opening_date": "01-01-2020",
            },
        ],
    )


def _context(root: Path) -> RunContext:
    accounts_path = _write_minimal_configs(root)
    with mock.patch.dict(os.environ, default_test_env(root), clear=True):
        settings = AppSettings.load(accounts_path)
    return RunContext(settings=settings, alerts=AlertService(handler=None))


def _account_download_dir(ctx: RunContext, account: ResolvedAccount) -> Path:
    return ctx.settings.download_path / "credit_card" / account.account_number


def _extract_account_result(
    ctx: RunContext, account: ResolvedAccount
) -> ExtractAccountResult:
    return ExtractAccountResult(
        bank=account.bank,
        download_dir=_account_download_dir(ctx, account),
        messages_matched=1,
        attachments_saved=1,
    )


def _cleanup_account_result(
    ctx: RunContext, account: ResolvedAccount
) -> CleanupAccountResult:
    return CleanupAccountResult(
        bank=account.bank,
        download_dir=_account_download_dir(ctx, account),
        unsupported_staging_removed=0,
        decrypted=1,
        prepared=1,
        rejected=0,
        orphans_removed=0,
        skipped=False,
    )


def _metadata_account_result(
    ctx: RunContext, account: ResolvedAccount
) -> MetadataAccountResult:
    return MetadataAccountResult(
        bank=account.bank,
        download_dir=_account_download_dir(ctx, account),
        output=_account_download_dir(ctx, account) / "metadata.json",
        statement_count=1,
    )


def _parse_account_result(
    ctx: RunContext, account: ResolvedAccount
) -> ParseAccountResult:
    return ParseAccountResult(
        bank=account.bank,
        download_dir=_account_download_dir(ctx, account),
        fy_results=(),
        total_transactions=0,
        total_statements=0,
    )


class RunnerTests(unittest.TestCase):
    @mock.patch("networthcsv.pipeline.runner.extract_stage.run_all")
    def test_run_extract_delegates_to_extract_stage(
        self, mock_run_all: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            mock_run_all.return_value = ExtractStageResult(accounts=())
            results = run_extract(ctx)
        mock_run_all.assert_called_once_with(ctx)
        self.assertEqual(results, ExtractStageResult(accounts=()))

    @mock.patch("networthcsv.pipeline.runner.cleanup_stage.run_account")
    def test_run_cleanup_delegates_to_cleanup_stage(
        self, mock_run_account: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            account = ctx.settings.accounts[0]
            mock_run_account.return_value = _cleanup_account_result(ctx, account)
            results = run_cleanup(ctx)
        mock_run_account.assert_called_once_with(ctx, account)
        self.assertEqual(len(results), 1)

    @mock.patch("networthcsv.pipeline.runner.metadata_stage.run_account")
    def test_run_metadata_delegates_to_metadata_stage(
        self, mock_run_account: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            account = ctx.settings.accounts[0]
            mock_run_account.return_value = _metadata_account_result(ctx, account)
            results = run_metadata(ctx)
        mock_run_account.assert_called_once_with(ctx, account)
        self.assertEqual(len(results), 1)

    @mock.patch("networthcsv.pipeline.runner.parse_stage.run_account")
    def test_run_parse_delegates_to_parse_stage(
        self, mock_run_account: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            account = ctx.settings.accounts[0]
            mock_run_account.return_value = _parse_account_result(ctx, account)
            results = run_parse(ctx)
        mock_run_account.assert_called_once_with(ctx, account)
        self.assertEqual(len(results), 1)

    @mock.patch("networthcsv.pipeline.runner.run_extract")
    @mock.patch("networthcsv.pipeline.runner.run_cleanup")
    @mock.patch("networthcsv.pipeline.runner.run_metadata")
    @mock.patch("networthcsv.pipeline.runner.run_parse")
    def test_run_pipeline_runs_all_stages(
        self,
        mock_parse: mock.MagicMock,
        mock_metadata: mock.MagicMock,
        mock_cleanup: mock.MagicMock,
        mock_extract: mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            account = ctx.settings.accounts[0]
            mock_extract.return_value = ExtractStageResult(
                accounts=(_extract_account_result(ctx, account),)
            )
            mock_cleanup.return_value = (_cleanup_account_result(ctx, account),)
            mock_metadata.return_value = (_metadata_account_result(ctx, account),)
            mock_parse.return_value = (_parse_account_result(ctx, account),)
            result = run_pipeline(ctx)
        self.assertIsInstance(result, PipelineResult)

    @mock.patch("networthcsv.runtime.run_pipeline")
    def test_process_delegates_to_run_pipeline(
        self, mock_run_pipeline: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            expected = PipelineResult(
                extract=ExtractStageResult(accounts=()),
                cleanup=(),
                metadata=(),
                parse=(),
            )
            mock_run_pipeline.return_value = expected
            result = process(ctx)
        mock_run_pipeline.assert_called_once_with(ctx)
        self.assertEqual(result, expected)

    @mock.patch("networthcsv.pipeline.cleanup.run_account")
    @mock.patch("networthcsv.pipeline.metadata.run_account")
    @mock.patch("networthcsv.pipeline.parse.parse.run_account")
    def test_process_upload_runs_post_upload_stages(
        self,
        mock_parse: mock.MagicMock,
        mock_metadata: mock.MagicMock,
        mock_cleanup: mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            account = ctx.settings.accounts[0]
            process_upload(ctx, account, source_format="pdf", statement_date="2024-01")
        mock_cleanup.assert_called_once()
        mock_metadata.assert_called_once()
        mock_parse.assert_called_once()

    def test_run_extract_raises_when_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            ctx = RunContext(
                settings=ctx.settings,
                alerts=ctx.alerts,
                should_cancel=lambda: True,
            )
            with self.assertRaises(JobCancelledError):
                run_extract(ctx)

    def test_run_cleanup_skips_missing_account_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = _write_minimal_configs(root)
            with mock.patch.dict(os.environ, default_test_env(root), clear=True):
                settings = AppSettings.load(accounts_path)
            account = settings.accounts[0]
            ctx = RunContext(
                settings=settings,
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
            with mock.patch.dict(os.environ, default_test_env(root), clear=True):
                settings = AppSettings.load(root / "accounts.json")
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

    def test_discover_account_fy_dirs_returns_sorted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts_path = _write_minimal_configs(root)
            with mock.patch.dict(os.environ, default_test_env(root), clear=True):
                settings = AppSettings.load(accounts_path)
            account = settings.accounts[0]
            fy_dir = (
                settings.download_path
                / "FY23-2024"
                / "credit_card"
                / account.account_number
            )
            _ = fy_dir.mkdir(parents=True)
            discovered = discover_account_fy_dirs(settings.download_path, account)
            self.assertEqual(discovered, [fy_dir])

    @mock.patch("networthcsv.pipeline.runner.run_extract")
    def test_run_pipeline_propagates_stage_error(
        self, mock_extract: mock.MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _context(Path(tmp))
            mock_extract.side_effect = StageError("extract failed")
            with self.assertRaises(StageError):
                _ = run_pipeline(ctx)
