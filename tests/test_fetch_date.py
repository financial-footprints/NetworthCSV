"""Last fetch date integration with get_statements."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from cleanup_support import account as make_account, run_context
from networthcsv.pipeline.get_statements import thunderbird as thunderbird_pipeline
from networthcsv.pipeline.metadata import read_last_fetch_date, write_last_fetch_date
from networthcsv.utils.account_dates import resolve_account_search_dates


class ExtractFetchDateTests(unittest.TestCase):
    @patch("networthcsv.pipeline.get_statements.thunderbird.write_last_fetch_date")
    @patch("networthcsv.pipeline.get_statements.thunderbird.discover_mbox_files")
    @patch("networthcsv.pipeline.get_statements.thunderbird.process_mbox")
    def test_extract_writes_last_fetch_date_after_success(
        self,
        mock_process_mbox: MagicMock,
        mock_discover: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            resolved_account = make_account()
            profile = download_path / "profile"
            _ = profile.mkdir()
            mock_discover.return_value = [profile / "INBOX"]
            mock_process_mbox.return_value = (0, 0)

            ctx = run_context(download_path)
            with patch(
                "networthcsv.pipeline.get_statements.thunderbird.date"
            ) as mock_date:
                mock_date.today.return_value = date(2026, 1, 20)
                _ = thunderbird_pipeline.extract_account(
                    profile,
                    resolved_account,
                    download_path
                    / resolved_account.account_type
                    / resolved_account.account_number,
                    None,
                    ctx,
                )

            mock_write.assert_called_once_with(
                download_path,
                resolved_account,
                date(2026, 1, 20),
            )

    def test_incremental_start_uses_last_fetch_minus_one_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            download_path = Path(tmp)
            resolved_account = make_account()
            _ = write_last_fetch_date(
                download_path, resolved_account, date(2026, 1, 20)
            )

            last_fetch = read_last_fetch_date(download_path, resolved_account)
            start, _end = resolve_account_search_dates(
                resolved_account,
                None,
                last_fetch_date=last_fetch,
            )

            self.assertEqual(start, date(2026, 1, 19))
