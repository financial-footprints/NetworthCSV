"""Settings loading tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from networthcsv.errors import ConfigError
from networthcsv.settings import (
    AppSettings,
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
    EmailSource,
    ResolvedAccount,
    RunSettings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)
from networthcsv.settings._validators import (
    normalize_account_number,
    normalize_bank,
    normalize_variant,
)
from networthcsv.settings.app_settings import _build_settings
from networthcsv.settings.env_settings import load_env_settings
from networthcsv.settings.models import UserAccountConfig, parse_accounts_config
from networthcsv.settings._load import ENV_PATH_KEY, ENV_PATH_VAR, reset_dotenv_state
from helpers import (
    isolated_environ,
    test_env,
    test_env_with_dotenv_chain,
    write_accounts,
)
from networthcsv.utils.account import account_label
from networthcsv.utils.account_dates import (
    parse_closing_date,
    parse_opening_date,
    resolve_account_search_dates,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.account_matching import AccountMatching
from networthcsv.utils.banks._matching_validators import (
    normalize_body_contains,
    normalize_from,
    normalize_text_contains,
    normalize_text_not_contains,
)
from networthcsv.utils.path import account_download_path
from fixtures.helpers import complete_email_alert_settings


_DEFAULT_PROFILE = Path("/profile")
_DEFAULT_DOWNLOAD_PATH = Path("/statements")


class SettingsTests(unittest.TestCase):
    def _write_json(self, path: Path, data: dict[str, object]) -> None:
        _ = path.write_text(json.dumps(data), encoding="utf-8")

    def _thunderbird_source(
        self, profile: Path = _DEFAULT_PROFILE
    ) -> ThunderbirdSource:
        return ThunderbirdSource(thunderbird=ThunderbirdSourceSettings(profile=profile))

    def _write_accounts(
        self,
        directory: Path,
        accounts: list[dict[str, object]],
    ) -> Path:
        return write_accounts(directory, accounts)

    def _load_settings(
        self,
        root: Path,
        accounts: list[dict[str, object]],
        **env_overrides: str,
    ) -> AppSettings:
        _ = (root / "profile").mkdir(exist_ok=True)
        _ = (root / "statements").mkdir(exist_ok=True)
        accounts_path = self._write_accounts(root, accounts)
        with test_env(root, **env_overrides):
            return AppSettings.load(accounts_path)

    def _account(self, **kwargs: object) -> dict[str, object]:
        data: dict[str, object] = {
            "account_number": "1234",
            "statement": {"text_contains": "1234"},
            "passwords": ["x"],
            "opening_date": "01-01-2020",
        }
        data.update(kwargs)
        return data

    def _settings(
        self,
        *,
        source: ThunderbirdSource | EmailSource | None = None,
        download_path: Path = _DEFAULT_DOWNLOAD_PATH,
        accounts: list[ResolvedAccount] | None = None,
        alerts: ConsoleAlertSettings | EmailAlertsSettings | None = None,
        run: RunSettings | None = None,
    ) -> AppSettings:
        return AppSettings(
            source=source or self._thunderbird_source(),
            download_path=download_path,
            accounts=accounts or [self._account_settings()],
            alerts=alerts,
            run=run or RunSettings(),
        )

    def _account_settings(
        self,
        *,
        bank: str = "bob",
        variant: str | None = None,
        account_number: str = "1234",
        text_contains: list[str] | str = "1234",
        subjects: list[str] | None = None,
        body_contains: list[str] | None = None,
        from_addresses: list[str] | None = None,
        passwords: list[str] | None = None,
        account_type: str = "credit_card",
    ) -> ResolvedAccount:
        statement_text_contains = (
            text_contains if isinstance(text_contains, list) else [text_contains]
        )
        return ResolvedAccount.model_validate(
            {
                "bank": bank,
                "variant": variant,
                "account_number": account_number,
                "type": account_type,
                "passwords": passwords or ["x"],
                "opening_date": "01-01-2020",
                "mail": {
                    "subjects": subjects or ["BOB"],
                    "body_contains": body_contains or [],
                    "from": from_addresses or [],
                },
                "statement": {
                    "text_contains": statement_text_contains,
                },
            }
        )

    def test_load_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            statements = root / "statements"
            profile = root / "profile"
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        passwords=["secret", "secret", "other"],
                    )
                ],
            )
            self.assertEqual(settings.source.type, "thunderbird")
            assert isinstance(settings.source, ThunderbirdSource)
            self.assertEqual(settings.source.thunderbird.profile, profile.resolve())
            self.assertEqual(settings.download_path, statements.resolve())
            self.assertEqual(settings.accounts[0].bank, "bob")
            self.assertIsNone(settings.accounts[0].variant)
            self.assertEqual(
                settings.accounts[0].mail.subjects,
                get_handler("bob", None).mail_subjects(),
            )
            self.assertEqual(settings.accounts[0].passwords, ["secret", "other"])
            self.assertEqual(settings.accounts[0].account_number, "1234")
            self.assertEqual(settings.accounts[0].statement.text_contains, ["1234"])
            self.assertEqual(settings.accounts[0].mail.body_contains, [])
            self.assertEqual(settings.accounts[0].mail.from_addresses, [])
            self.assertEqual(settings.accounts[0].account_type, "credit_card")

    def test_bodies_and_from_from_handler_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="federal", variant="signet")],
            )
            handler = get_handler("federal", "signet")
            account = settings.accounts[0]
            self.assertEqual(account.mail.body_contains, handler.mail_body_contains())
            self.assertEqual(account.mail.from_addresses, handler.mail_from_addresses())

    def test_user_override_bodies_and_from(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="federal",
                        variant="signet",
                        mail={
                            "body_contains": ["custom body"],
                            "from": ["custom@bank.com"],
                        },
                    )
                ],
            )
            account = settings.accounts[0]
            self.assertEqual(account.mail.body_contains, ["custom body"])
            self.assertEqual(account.mail.from_addresses, ["custom@bank.com"])

    def test_catch_all_uses_default_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="icici")],
            )
            handler = get_handler("icici", None)
            account = settings.accounts[0]
            self.assertEqual(account.mail.subjects, handler.mail_subjects())
            self.assertEqual(account.mail.body_contains, [])
            self.assertEqual(account.mail.from_addresses, [])

    def test_normalize_helpers(self) -> None:
        self.assertEqual(normalize_bank("bob"), "bob")
        self.assertEqual(normalize_bank("BOB"), "bob")
        with self.assertRaises(ValueError):
            _ = normalize_bank("")
        with self.assertRaises(ValueError):
            _ = normalize_bank("hdfc/swiggy")

        self.assertEqual(normalize_variant("amazon"), "amazon")
        self.assertEqual(normalize_variant("Amazon"), "amazon")
        self.assertIsNone(normalize_variant(None))
        self.assertIsNone(normalize_variant(""))
        with self.assertRaises(ValueError):
            _ = normalize_variant("swiggy/primary")

        self.assertEqual(normalize_account_number("1234"), "1234")
        self.assertEqual(normalize_account_number("  XXXX 5678  "), "XXXX 5678")
        with self.assertRaises(ValueError):
            _ = normalize_account_number("")
        with self.assertRaises(ValueError):
            _ = normalize_account_number("   ")

        self.assertEqual(normalize_text_contains("1234"), ["1234"])
        self.assertEqual(normalize_text_contains("  XXXX 5678  "), ["XXXX 5678"])
        self.assertEqual(normalize_text_contains(["1234", "5678"]), ["1234", "5678"])
        self.assertEqual(normalize_text_contains(""), [])
        self.assertEqual(normalize_text_contains(None), [])
        self.assertEqual(normalize_text_contains([]), [])

        self.assertEqual(normalize_text_not_contains("Anotherthing"), ["Anotherthing"])
        self.assertEqual(
            normalize_text_not_contains(["A", " B "]),
            ["A", "B"],
        )
        self.assertEqual(normalize_text_not_contains(""), [])
        self.assertEqual(normalize_text_not_contains(None), [])
        self.assertEqual(normalize_text_not_contains([]), [])

        self.assertEqual(normalize_body_contains(["A", "a", " B "]), ["A", "B"])
        self.assertEqual(normalize_body_contains(None), [])
        self.assertEqual(normalize_body_contains(""), [])

        with self.assertRaises(ValueError):
            _ = normalize_from(["not-an-email@"])
        with self.assertRaises(ValueError):
            _ = normalize_from(["bad entry"])

    def test_load_with_opening_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(bank="bob", opening_date="01-04-2023"),
                ],
            )
            self.assertEqual(settings.accounts[0].opening_date, date(2023, 4, 1))

    def test_load_with_closing_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        opening_date="01-04-2023",
                        closing_date="01-08-2024",
                    ),
                ],
            )
            self.assertEqual(settings.accounts[0].closing_date, date(2024, 8, 1))

    def test_omitted_closing_date_means_account_open(self) -> None:
        account = UserAccountConfig.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": "01-04-2023",
            }
        )
        self.assertIsNone(account.closing_date)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob", opening_date="01-04-2023")],
            )
            self.assertIsNone(settings.accounts[0].closing_date)

    def test_closing_date_before_opening_date_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "01-08-2024",
                    "closing_date": "01-04-2023",
                }
            )

    def test_resolve_account_search_dates_uses_opening_date(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "mail": {"subjects": ["stmt"]},
                "opening_date": date(2023, 4, 1),
                "closing_date": date(2024, 8, 1),
            }
        )
        start, end = resolve_account_search_dates(account)
        self.assertEqual(start, date(2023, 4, 1))
        self.assertEqual(end, date(2024, 8, 2))

    def test_resolve_account_search_dates_uses_last_fetch_minus_one_day(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "mail": {"subjects": ["stmt"]},
                "opening_date": date(2023, 4, 1),
            }
        )
        start, _end = resolve_account_search_dates(
            account,
            last_fetch_date=date(2026, 1, 20),
        )
        self.assertEqual(start, date(2026, 1, 19))

        start, _end = resolve_account_search_dates(account)
        self.assertEqual(start, date(2023, 4, 1))

    def test_resolve_account_search_dates_uses_day_after_closing(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": date(2020, 1, 1),
                "mail": {"subjects": ["stmt"]},
                "closing_date": date(2024, 2, 1),
            }
        )
        _start, end = resolve_account_search_dates(account)
        self.assertEqual(end, date(2024, 2, 2))

    def test_invalid_opening_date_format(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_opening_date("2023-04")
        with self.assertRaises(ValueError):
            _ = parse_opening_date("32-01-2024")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "04-2023",
                }
            )

    def test_opening_date_accepts_iso_format(self) -> None:
        self.assertEqual(parse_opening_date("2023-04-01"), date(2023, 4, 1))
        current_year = date.today().year
        account = UserAccountConfig.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": f"{current_year}-12-31",
            }
        )
        self.assertEqual(account.opening_date, date(current_year, 12, 31))

    def test_opening_date_rejects_dates_after_current_year(self) -> None:
        future_year = date.today().year + 1
        with self.assertRaises(ValueError):
            _ = parse_opening_date(f"01-01-{future_year}")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": f"01-01-{future_year}",
                }
            )

    def test_opening_date_rejects_dates_before_1970(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_opening_date("31-12-1969")
        with self.assertRaises(ValueError):
            _ = parse_opening_date("31-03-0145")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "31-03-0145",
                }
            )

    def test_opening_date_accepts_1970_01_01(self) -> None:
        self.assertEqual(parse_opening_date("01-01-1970"), date(1970, 1, 1))

    def test_invalid_closing_date_format(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_closing_date("2024-08")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "01-01-2020",
                    "closing_date": "08-2024",
                }
            )

    def test_missing_opening_date_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                }
            )

    def test_text_not_contains_unions_bank_defaults_with_user_markers(self) -> None:
        defaults = get_handler("indusind", "auraedge").matching_defaults()
        user = UserAccountConfig.model_validate(
            {
                "bank": "indusind",
                "variant": "auraedge",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": "01-01-2020",
                "statement": {"text_not_contains": ["USER MARKER"]},
            }
        )
        merged = AccountMatching.merge(defaults, user)
        self.assertIn("ANNUAL SPEND SUMMARY", merged.statement.text_not_contains)
        self.assertIn("USER MARKER", merged.statement.text_not_contains)

        cleared = UserAccountConfig.model_validate(
            {
                "bank": "indusind",
                "variant": "auraedge",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": "01-01-2020",
                "statement": {"text_not_contains": []},
            }
        )
        merged_cleared = AccountMatching.merge(defaults, cleared)
        self.assertIn(
            "ANNUAL SPEND SUMMARY",
            merged_cleared.statement.text_not_contains,
        )

    def test_user_override_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        mail={"subjects": ["Custom BOB subject for testing"]},
                    )
                ],
            )
            self.assertEqual(
                settings.accounts[0].mail.subjects,
                ["Custom BOB subject for testing"],
            )

    def test_handler_provides_mail_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(bank="bob"),
                    self._account(
                        bank="bob",
                        variant="easy",
                        account_number="5678",
                        passwords=["y"],
                    ),
                ],
            )
            self.assertEqual(
                settings.accounts[0].mail.subjects,
                get_handler("bob", None).mail_subjects(),
            )
            self.assertEqual(
                settings.accounts[1].mail.subjects,
                get_handler("bob", "easy").mail_subjects(),
            )

    def test_unknown_bank_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ConfigError):
                _ = self._load_settings(
                    root,
                    accounts=[self._account(bank="missing")],
                )

    def test_load_accounts_by_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob")],
            )
            self.assertEqual(settings.accounts[0].bank, "bob")

    def test_from_user_accounts_allow_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root):
                settings = AppSettings.from_user_accounts([], allow_empty=True)
            self.assertEqual(settings.accounts, [])

    def test_from_user_accounts_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root):
                settings = AppSettings.from_user_accounts(
                    [self._account(bank="bob")],
                )
            self.assertEqual(settings.accounts[0].bank, "bob")

    def test_missing_account_number_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ConfigError):
                _ = self._load_settings(
                    root,
                    accounts=[{"bank": "bob", "passwords": ["x"]}],
                )

    def test_duplicate_account_number_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_accounts_config(
                [
                    self._account(bank="bob"),
                    self._account(bank="icici", passwords=["y"]),
                ],
            )

    def test_same_bank_variant_different_account_numbers_allowed(self) -> None:
        accounts = parse_accounts_config(
            [
                self._account(
                    bank="icici",
                    variant="amazon",
                    account_number="1111",
                ),
                self._account(
                    bank="icici",
                    variant="amazon",
                    account_number="2222",
                    passwords=["y"],
                ),
            ],
        )
        self.assertEqual(len(accounts), 2)

    def test_catch_all_and_variant_accounts_allowed(self) -> None:
        accounts = parse_accounts_config(
            [
                self._account(bank="icici"),
                self._account(bank="icici", variant="amazon", passwords=["y"]),
            ],
        )
        self.assertEqual(len(accounts), 2)

    def test_log_level_defaults_to_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root):
                env_settings = load_env_settings()
            self.assertEqual(env_settings.log_level, "info")

    def test_log_level_accepts_debug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root, LOG_LEVEL="debug"):
                env_settings = load_env_settings()
            self.assertEqual(env_settings.log_level, "debug")

    def test_log_level_rejects_invalid_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root, LOG_LEVEL="trace"):
                with self.assertRaises(ValueError):
                    _ = load_env_settings()

    def test_account_download_path_uses_account_type(self) -> None:
        settings = self._settings(
            accounts=[
                self._account_settings(
                    bank="hdfc",
                    variant="swiggy",
                    subjects=["Swiggy statement"],
                )
            ],
        )
        self.assertEqual(
            account_download_path(settings.download_path, settings.accounts[0]),
            Path("/statements/credit_card/1234"),
        )

    def test_account_download_path_bank_account_type(self) -> None:
        settings = self._settings(
            accounts=[
                self._account_settings(
                    bank="bob",
                    variant="savings",
                    account_type="bank_account",
                    subjects=["BOB savings"],
                )
            ],
        )
        self.assertEqual(
            account_download_path(settings.download_path, settings.accounts[0]),
            Path("/statements/bank_account/1234"),
        )

    def test_icici_variant_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="icici", variant="amazon", account_number="1111"
                    ),
                    self._account(
                        bank="icici",
                        variant="platinum",
                        account_number="2222",
                        passwords=["y"],
                    ),
                    self._account(bank="icici", account_number="3333", passwords=["z"]),
                ],
            )
            amazon = settings.accounts[0]
            platinum = settings.accounts[1]
            catch_all = settings.accounts[2]
            self.assertEqual(
                amazon.mail.subjects,
                get_handler("icici", "amazon").mail_subjects(),
            )
            self.assertEqual(
                platinum.mail.subjects,
                get_handler("icici", None).mail_subjects(),
            )
            self.assertEqual(platinum.variant, "platinum")
            self.assertEqual(
                catch_all.mail.subjects,
                get_handler("icici", None).mail_subjects(),
            )

    def test_unknown_variant_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="icici", variant="missing")],
            )
            account = settings.accounts[0]
            self.assertEqual(account.variant, "missing")
            self.assertEqual(
                account.mail.subjects,
                get_handler("icici", None).mail_subjects(),
            )

    def test_unknown_variant_user_bodies_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(
                        bank="icici",
                        variant="missing",
                        account_number="test2",
                        mail={"body_contains": ["XX1001"]},
                        passwords=["test"],
                    )
                ],
            )
            account = settings.accounts[0]
            self.assertEqual(account.variant, "missing")
            self.assertEqual(
                account.mail.subjects,
                get_handler("icici", None).mail_subjects(),
            )
            self.assertEqual(account.mail.body_contains, ["XX1001"])

    def test_variant_normalization(self) -> None:
        account = UserAccountConfig.model_validate(
            {
                "bank": "hdfc",
                "variant": "Swiggy",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": "01-01-2020",
            }
        )
        self.assertEqual(account.variant, "swiggy")

    def test_account_label(self) -> None:
        with_variant = self._account_settings(
            bank="icici",
            variant="amazon",
            subjects=["Amazon"],
        )
        without_variant = self._account_settings(
            bank="icici",
            variant=None,
            account_number="5678",
            subjects=["Amazon"],
        )
        self.assertEqual(account_label(with_variant), "icici/amazon (1234)")
        self.assertEqual(account_label(without_variant), "icici (5678)")

    def test_missing_source_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = write_accounts(root, [self._account(bank="bob")])
            with test_env(root, SOURCE_TYPE=""):
                with self.assertRaises(ValueError):
                    _ = load_env_settings()

    def test_explicit_thunderbird_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob")],
                THUNDERBIRD_PROFILE=str(profile),
            )
            assert isinstance(settings.source, ThunderbirdSource)
            self.assertEqual(settings.source.thunderbird.profile, profile.resolve())

    def test_email_source_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob")],
                SOURCE_TYPE="email",
                IMAP_HOST="imap.gmail.com",
                IMAP_USERNAME="user@gmail.com",
                IMAP_PASSWORD="secret",
                IMAP_FOLDER="[Gmail]/All Mail",
            )
            assert isinstance(settings.source, EmailSource)
            self.assertEqual(settings.source.email.host, "imap.gmail.com")
            self.assertEqual(settings.source.email.folder, "[Gmail]/All Mail")

    def test_password_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ConfigError):
                _ = self._load_settings(
                    root,
                    accounts=[{"bank": "bob", "password": "legacy"}],
                )

    def test_build_settings_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts = parse_accounts_config(
                [self._account(bank="bob", passwords=["secret"])],
            )
            with test_env(root):
                env_settings = load_env_settings()
            settings = _build_settings(accounts, env_settings)
            self.assertEqual(
                settings.accounts[0].mail.subjects,
                get_handler("bob", None).mail_subjects(),
            )
            self.assertEqual(settings.accounts[0].passwords, ["secret"])

    def test_alerts_default_to_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with test_env(root):
                env_settings = load_env_settings()
            assert isinstance(env_settings.alerts, ConsoleAlertSettings)

    def test_alerts_console_type(self) -> None:
        settings = ConsoleAlertSettings()
        self.assertEqual(settings.type, "console")

    def test_alerts_email_requires_nested_settings(self) -> None:
        with self.assertRaises(ValidationError):
            _ = EmailAlertsSettings.model_validate({"type": "email"})

    def test_alerts_email_rejects_empty_password(self) -> None:
        with self.assertRaises(ValidationError):
            _ = EmailAlertsSettings(
                email=EmailAlertSettings(
                    smtp_host="smtp.example.com",
                    smtp_port=587,
                    username="user@example.com",
                    password="",
                    from_address="user@example.com",
                    to=["alerts@example.com"],
                ),
            )

    def test_alerts_console_rejects_email_block(self) -> None:
        with self.assertRaises(ValidationError):
            _ = ConsoleAlertSettings.model_validate(
                {
                    "type": "console",
                    "email": complete_email_alert_settings().model_dump(),
                }
            )

    def test_alerts_config_merged_into_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob")],
                ALERTS_TYPE="email",
                SMTP_HOST="smtp.example.com",
                SMTP_PORT="587",
                SMTP_USERNAME="user@example.com",
                SMTP_PASSWORD="secret",
                SMTP_FROM_ADDRESS="user@example.com",
                SMTP_TO="alerts@example.com",
            )
            self.assertIsNotNone(settings.alerts)
            assert settings.alerts is not None
            self.assertEqual(settings.alerts.type, "email")
            assert isinstance(settings.alerts, EmailAlertsSettings)
            self.assertEqual(settings.alerts.email.smtp_host, "smtp.example.com")

    def test_env_path_chain_loads_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "leaf.env"
            _ = leaf.write_text("DOWNLOAD_PATH=/leaf/statements\n", encoding="utf-8")
            bridge = root / "bridge.env"
            _ = bridge.write_text(f"{ENV_PATH_KEY}={leaf}\n", encoding="utf-8")
            start = root / ".env"
            _ = start.write_text(f"{ENV_PATH_KEY}={bridge}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "networthcsv.settings._load._DEFAULT_ENV_PATH",
                    start,
                ):
                    reset_dotenv_state()
                    with test_env_with_dotenv_chain(root):
                        env_settings = load_env_settings()
            self.assertEqual(env_settings.download_path, Path("/leaf/statements"))

    def test_env_path_chain_merges_additive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "leaf.env"
            _ = leaf.write_text(
                "OVERRIDE_ME=leaf_value\nNEW_IN_LEAF=leaf_only\n",
                encoding="utf-8",
            )
            bridge = root / "bridge.env"
            _ = bridge.write_text(
                f"{ENV_PATH_KEY}={leaf}\nOVERRIDE_ME=start_value\n",
                encoding="utf-8",
            )
            start = root / ".env"
            _ = start.write_text(
                f"{ENV_PATH_KEY}={bridge}\nKEEP_ME=from_start\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "networthcsv.settings._load._DEFAULT_ENV_PATH",
                    start,
                ):
                    reset_dotenv_state()
                    with test_env_with_dotenv_chain(root):
                        _ = load_env_settings()
                        self.assertEqual(os.environ.get("KEEP_ME"), "from_start")
                        self.assertEqual(os.environ.get("OVERRIDE_ME"), "leaf_value")
                        self.assertEqual(os.environ.get("NEW_IN_LEAF"), "leaf_only")

    def test_env_path_max_depth_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.env"
            b = root / "b.env"
            _ = a.write_text(f"{ENV_PATH_KEY}={b}\n", encoding="utf-8")
            _ = b.write_text(f"{ENV_PATH_KEY}={a}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "networthcsv.settings._load._DEFAULT_ENV_PATH",
                    a,
                ):
                    reset_dotenv_state()
                    with self.assertRaisesRegex(ConfigError, "maximum depth"):
                        with test_env_with_dotenv_chain(root):
                            _ = load_env_settings()

    def test_env_networthcsv_start_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            custom = root / "custom.env"
            _ = custom.write_text(
                "\n".join(
                    [
                        "DOWNLOAD_PATH=/custom/statements",
                        "SOURCE_TYPE=thunderbird",
                        f"THUNDERBIRD_PROFILE={root / 'profile'}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {ENV_PATH_VAR: str(custom)},
                clear=True,
            ):
                reset_dotenv_state()
                env_settings = load_env_settings()
            self.assertEqual(env_settings.download_path, Path("/custom/statements"))

    def test_resolve_config_path_default(self) -> None:
        with isolated_environ():
            self.assertEqual(
                AppSettings.resolve_config_path(None),
                AppSettings.DEFAULT_CONFIG_PATH.resolve(),
            )

    def test_resolve_config_path_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.accounts.json"
            _ = custom.write_text("[]", encoding="utf-8")
            with isolated_environ(**{AppSettings.CONFIG_ENV_VAR: str(custom)}):
                self.assertEqual(
                    AppSettings.resolve_config_path(None), custom.resolve()
                )

    def test_resolve_config_path_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.accounts.json"
            _ = custom.write_text("[]", encoding="utf-8")
            with isolated_environ(
                **{AppSettings.CONFIG_ENV_VAR: "/other/accounts.json"}
            ):
                self.assertEqual(
                    AppSettings.resolve_config_path(custom), custom.resolve()
                )

    def test_resolve_config_path_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = root / "custom.accounts.json"
            _ = custom.write_text("[]", encoding="utf-8")
            env_path = root / ".env"
            _ = env_path.write_text(
                f"{AppSettings.CONFIG_ENV_VAR}={custom}\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "networthcsv.settings._load._DEFAULT_ENV_PATH",
                    env_path,
                ):
                    reset_dotenv_state()
                    self.assertEqual(
                        AppSettings.resolve_config_path(None),
                        custom.resolve(),
                    )

    def test_run_settings_applied_at_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(bank="bob", variant="easy", account_number="5678")
                ],
            )
            updated = settings.with_run(
                RunSettings(identifier="5678", financial_year="FY23-2024")
            )
            self.assertEqual(updated.run.identifier, "5678")
            self.assertEqual(updated.run.financial_year, "FY23-2024")

    def test_accounts_to_run_filters_by_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[
                    self._account(bank="bob", variant="easy", account_number="1"),
                    self._account(bank="pnb", variant="platinum", account_number="2"),
                ],
            )
            settings = settings.with_run(RunSettings(identifier="1"))
            selected = settings.accounts_to_run()
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].bank, "bob")
            self.assertEqual(selected[0].account_number, "1")

    def test_validate_run_filter_raises_when_identifier_no_match(self) -> None:
        settings = self._settings(
            accounts=[
                self._account_settings(bank="bob", variant="easy", account_number="1"),
            ],
            run=RunSettings(identifier="missing"),
        )
        with self.assertRaises(ValueError):
            settings.validate_run_filter()

    def test_run_settings_model_defaults(self) -> None:
        run = RunSettings()
        self.assertIsNone(run.identifier)
        self.assertIsNone(run.financial_year)

    def test_account_type_defaults_to_credit_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._load_settings(
                root,
                accounts=[self._account(bank="bob")],
            )
            self.assertEqual(settings.accounts[0].account_type, "credit_card")


if __name__ == "__main__":
    _ = unittest.main()
