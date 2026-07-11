"""Golden tests for bank statement fixtures under tests/fixtures/."""

from __future__ import annotations

import unittest

from networthcsv.pipeline.cleanup.statement_date import resolve_month_period
from networthcsv.pipeline.metadata.metadata import _resolve_statement_period
from networthcsv.utils.banks.helpers.amounts import balances_match
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from fixtures.helpers import (
    FIXTURES_ROOT,
    MANIFEST_PATH,
    REQUIRED_MANIFEST_KEYS,
    list_fixture_paths,
    load_manifest,
)

_DUMMY_FILENAME = "dummy__2099-99-99.pdf"


def _account(*, bank: str, variant: str | None) -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class MetadataFixtureManifestTests(unittest.TestCase):
    def test_manifest_file_exists(self) -> None:
        self.assertTrue(MANIFEST_PATH.is_file(), f"missing manifest: {MANIFEST_PATH}")

    def test_every_fixture_file_listed_in_manifest(self) -> None:
        manifest = load_manifest()
        fixture_paths = list_fixture_paths()
        self.assertGreater(len(fixture_paths), 0)
        missing = [path for path in fixture_paths if path not in manifest]
        self.assertEqual(missing, [])

    def test_every_manifest_entry_has_fixture_file(self) -> None:
        manifest = load_manifest()
        fixture_paths = set(list_fixture_paths())
        missing_files = [rel for rel in manifest if rel not in fixture_paths]
        self.assertEqual(missing_files, [])

    def test_manifest_entries_have_required_keys(self) -> None:
        for rel, entry in load_manifest().items():
            with self.subTest(fixture=rel):
                for key in REQUIRED_MANIFEST_KEYS:
                    self.assertIn(key, entry, f"{rel}: missing {key!r}")


class MetadataFixtureGoldenTests(unittest.TestCase):
    """Extract statement month and balances from every fixture; compare to manifest."""

    def test_all_fixtures_match_manifest(self) -> None:
        if not FIXTURES_ROOT.is_dir():
            self.skipTest(f"fixtures not found: {FIXTURES_ROOT}")

        manifest = load_manifest()
        failures: list[str] = []

        for rel, expected in sorted(manifest.items()):
            parts = rel.split("/")
            if len(parts) < 3:
                continue

            sample_path = FIXTURES_ROOT / rel
            if not sample_path.is_file():
                failures.append(f"{rel}: fixture file missing")
                continue

            bank, variant = parts[0], parts[1]
            text = sample_path.read_text(encoding="utf-8")
            account = _account(bank=bank, variant=variant)
            handler = get_handler(account.bank, account.variant)

            expected_month = expected.get("statement_month")
            if expected_month:
                actual_month = resolve_month_period(
                    text, _DUMMY_FILENAME, account=account
                )
                if actual_month != expected_month:
                    failures.append(
                        f"{rel}: month expected {expected_month!r}, got {actual_month!r}",
                    )

            opening = handler.get_opening_balance(text)
            closing = handler.get_closing_balance(text)

            expected_opening = expected.get("opening")
            expected_closing = expected.get("closing")

            if expected_opening is not None and (
                opening is None or not balances_match(opening, expected_opening)
            ):
                failures.append(
                    f"{rel}: opening expected {expected_opening!r}, got {opening!r}",
                )
            if expected_closing is not None and (
                closing is None or not balances_match(closing, expected_closing)
            ):
                failures.append(
                    f"{rel}: closing expected {expected_closing!r}, got {closing!r}",
                )

            expected_period_start = expected.get("period_start")
            expected_period_end = expected.get("period_end")
            if expected_period_start and expected_period_end:
                period_start_iso, period_end_iso, _ = _resolve_statement_period(
                    text,
                    account=account,
                )
                if period_start_iso != expected_period_start:
                    failures.append(
                        f"{rel}: period_start expected {expected_period_start!r}, "
                        f"got {period_start_iso!r}",
                    )
                if period_end_iso != expected_period_end:
                    failures.append(
                        f"{rel}: period_end expected {expected_period_end!r}, "
                        f"got {period_end_iso!r}",
                    )

        self.assertEqual(failures, [])


if __name__ == "__main__":
    _ = unittest.main()
