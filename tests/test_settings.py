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

from src.settings import (
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
    EmailSource,
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
    UserAccountConfig,
    UserConfig,
    account_download_path,
    account_label,
    accounts_to_run,
    CONFIG_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    load_app_config,
    load_settings,
    load_user_config,
    merge_settings,
    normalize_bank,
    normalize_bodies,
    normalize_from,
    normalize_identifier,
    normalize_variant,
    resolve_config_path,
)

_DEFAULT_PROFILE = Path("/profile")
_DEFAULT_DOWNLOAD_PATH = Path("/statements")


def _complete_email_alert_settings() -> EmailAlertSettings:
    return EmailAlertSettings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="user@example.com",
        password="secret",
        from_address="user@example.com",
        to=["alerts@example.com"],
    )


class SettingsTests(unittest.TestCase):
    def _write_json(self, path: Path, data: dict[str, object]) -> None:
        _ = path.write_text(json.dumps(data), encoding="utf-8")

    def _bob_bank_config(self) -> dict[str, object]:
        return {
            "default": {"subjects": ["BOB"]},
            "easy": {"subjects": ["BOB CREDIT CARD"]},
        }

    def _icici_bank_config(self) -> dict[str, object]:
        return {
            "default": {
                "subjects": ["ICICI Bank Credit Card Statement for the period"],
            },
            "amazon": {
                "subjects": [
                    "Amazon Pay ICICI Bank Credit Card Statement for the period"
                ],
            },
        }

    def _write_app_config(self, directory: Path, user_config: str, banks: dict[str, object]) -> Path:
        config_path = directory / "app.config.json"
        self._write_json(
            config_path,
            {
                "user_config": user_config,
                "banks": banks,
            },
        )
        return config_path

    def _write_app_config_overlay(
        self,
        directory: Path,
        overlay: dict[str, object],
    ) -> Path:
        config_path = directory / "app.config.local.json"
        self._write_json(config_path, overlay)
        return config_path

    def _thunderbird_source(self, profile: Path = _DEFAULT_PROFILE) -> ThunderbirdSource:
        return ThunderbirdSource(thunderbird=ThunderbirdSourceSettings(profile=profile))

    def _user_config_payload(
        self,
        *,
        download_path: str | Path = "/statements",
        profile: str | Path = "/profile",
        accounts: list[dict[str, object]],
        **extra: object,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "source": {
                "type": "thunderbird",
                "thunderbird": {"profile": str(profile)},
            },
            "download_path": str(download_path),
            "accounts": accounts,
        }
        data.update(extra)
        return data

    def _write_user_config(
        self,
        directory: Path,
        *,
        profile: str = "profile",
        download_path: str = "statements",
        accounts: list[dict[str, object]],
        start_date: str | None = None,
        source: dict[str, object] | None = None,
        extra: dict[str, object] | None = None,
    ) -> Path:
        config_path = directory / "user.config.json"
        data: dict[str, object] = {
            "download_path": download_path,
            "accounts": accounts,
            "source": source
            or {
                "type": "thunderbird",
                "thunderbird": {"profile": profile},
            },
        }
        if start_date is not None:
            data["start_date"] = start_date
        if extra:
            data.update(extra)
        self._write_json(config_path, data)
        return config_path

    def _account(self, **kwargs: object) -> dict[str, object]:
        data: dict[str, object] = {"identifier": "1234", "passwords": ["x"]}
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
        start_date: date | None = None,
    ) -> Settings:
        return Settings(
            source=source or self._thunderbird_source(),
            download_path=download_path,
            accounts=accounts or [self._account_settings()],
            alerts=alerts,
            run=run or RunSettings(),
            start_date=start_date,
        )

    def _account_settings(
        self,
        *,
        bank: str = "bob",
        variant: str | None = None,
        identifier: str = "1234",
        subjects: list[str] | None = None,
        bodies: list[str] | None = None,
        from_filters: list[str] | None = None,
        passwords: list[str] | None = None,
        start_marker: str | None = None,
        end_marker: str | None = None,
        information_markers: list[str] | None = None,
    ) -> ResolvedAccount:
        return ResolvedAccount.model_validate(
            {
                "bank": bank,
                "variant": variant,
                "identifier": identifier,
                "subjects": subjects or ["BOB"],
                "bodies": bodies or [],
                "from": from_filters or [],
                "passwords": passwords or ["x"],
                "start_marker": start_marker,
                "end_marker": end_marker,
                "information_markers": information_markers or [],
            }
        )

    def test_load_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            statements = root / "statements"
            _ = statements.mkdir()
            profile = root / "profile"
            _ = profile.mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        passwords=["secret", "secret", "other"],
                    )
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.source.type, "thunderbird")
            assert isinstance(settings.source, ThunderbirdSource)
            self.assertEqual(settings.source.thunderbird.profile, profile.resolve())
            self.assertEqual(settings.download_path, statements.resolve())
            self.assertEqual(settings.accounts[0].bank, "bob")
            self.assertIsNone(settings.accounts[0].variant)
            self.assertEqual(settings.accounts[0].subjects, ["BOB"])
            self.assertEqual(settings.accounts[0].passwords, ["secret", "other"])
            self.assertEqual(settings.accounts[0].identifier, "1234")
            self.assertEqual(settings.accounts[0].bodies, [])
            self.assertEqual(settings.accounts[0].from_filters, [])

    def test_bodies_and_from_from_variant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici", variant="amazon")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "default": {"subjects": ["ICICI default"]},
                        "amazon": {
                            "subjects": ["Amazon Pay ICICI"],
                            "bodies": ["Amazon Pay ICICI Bank Credit Card"],
                            "from": ["icicibank.com"],
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.bodies, ["Amazon Pay ICICI Bank Credit Card"])
            self.assertEqual(account.from_filters, ["icicibank.com"])

    def test_user_override_bodies_and_from(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    {
                        **self._account(
                            bank="icici",
                            variant="amazon",
                            bodies=["custom body"],
                        ),
                        "from": ["custom@bank.com"],
                    }
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "default": {"subjects": ["ICICI default"]},
                        "amazon": {
                            "subjects": ["Amazon Pay ICICI"],
                            "bodies": ["app body"],
                            "from": ["icicibank.com"],
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.bodies, ["custom body"])
            self.assertEqual(account.from_filters, ["custom@bank.com"])

    def test_catch_all_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "default": {
                            "subjects": ["ICICI generic"],
                            "bodies": ["Default body"],
                            "from": ["default.bank.com"],
                        },
                        "amazon": {
                            "subjects": ["Amazon Pay ICICI"],
                            "bodies": ["Amazon body"],
                            "from": ["amazon.bank.com"],
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.subjects, ["ICICI generic"])
            self.assertEqual(account.bodies, ["Default body"])
            self.assertEqual(account.from_filters, ["default.bank.com"])

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

        self.assertEqual(normalize_identifier("1234"), "1234")
        self.assertEqual(normalize_identifier("  XXXX 5678  "), "XXXX 5678")
        with self.assertRaises(ValueError):
            _ = normalize_identifier("")
        with self.assertRaises(ValueError):
            _ = normalize_identifier("   ")

        self.assertEqual(normalize_bodies(["A", "a", " B "]), ["A", "B"])
        self.assertEqual(normalize_bodies(None), [])
        self.assertEqual(normalize_bodies(""), [])

        with self.assertRaises(ValueError):
            _ = normalize_from(["not-an-email@"])
        with self.assertRaises(ValueError):
            _ = normalize_from(["bad entry"])

    def test_load_with_start_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                start_date="2024-06-01",
                accounts=[self._account(bank="bob")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.start_date, date(2024, 6, 1))

    def test_text_extract_markers_from_variant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="pnb", variant="platinum")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "pnb": {
                        "default": {"subjects": ["PNB default"]},
                        "platinum": {
                            "subjects": ["PNB statement"],
                            "start_marker": "Transaction Date",
                            "end_marker": "End of Statement",
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.start_marker, "Transaction Date")
            self.assertEqual(account.end_marker, "End of Statement")

    def test_information_markers_from_variant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="pnb", variant="platinum")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "pnb": {
                        "default": {"subjects": ["PNB default"]},
                        "platinum": {
                            "subjects": ["PNB statement"],
                            "information_markers": [
                                "TAD for the month consists of current month purchases"
                            ],
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(
                settings.accounts[0].information_markers,
                ["TAD for the month consists of current month purchases"],
            )

    def test_user_override_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        subjects=["Custom BOB subject for testing"],
                    )
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {"subjects": ["E-statement for your BOB"]}
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(
                settings.accounts[0].subjects,
                ["Custom BOB subject for testing"],
            )

    def test_missing_bank_in_app_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="missing")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_relative_user_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            app_config = load_app_config(app_config_path)
            self.assertEqual(app_config.user_config, (root / "user.config.json").resolve())

    def test_missing_identifier_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[{"bank": "bob", "passwords": ["x"]}],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_duplicate_account_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    accounts=[
                        self._account(bank="bob"),
                        self._account(bank="bob", passwords=["y"]),
                    ],
                )
            )

    def test_duplicate_variant_account_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    accounts=[
                        self._account(bank="icici", variant="amazon"),
                        self._account(bank="icici", variant="amazon", passwords=["y"]),
                    ],
                )
            )

    def test_catch_all_and_variant_accounts_allowed(self) -> None:
        user = UserConfig.model_validate(
            self._user_config_payload(
                accounts=[
                    self._account(bank="icici"),
                    self._account(bank="icici", variant="amazon", passwords=["y"]),
                ],
            )
        )
        self.assertEqual(len(user.accounts), 2)

    def test_log_level_defaults_to_info(self) -> None:
        user = UserConfig.model_validate(
            self._user_config_payload(
                accounts=[self._account(bank="bob")],
            )
        )
        self.assertEqual(user.log_level, "info")

    def test_log_level_accepts_debug(self) -> None:
        user = UserConfig.model_validate(
            self._user_config_payload(
                accounts=[self._account(bank="bob")],
                log_level="debug",
            )
        )
        self.assertEqual(user.log_level, "debug")

    def test_log_level_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    accounts=[self._account(bank="bob")],
                    log_level="trace",
                )
            )

    def test_account_download_path_with_variant(self) -> None:
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
            account_download_path(settings, settings.accounts[0]),
            Path("/statements/hdfc/swiggy"),
        )

    def test_account_download_path_without_variant(self) -> None:
        settings = self._settings(
            accounts=[
                self._account_settings(
                    bank="icici",
                    variant=None,
                    subjects=["Amazon subject", "Premium subject"],
                )
            ],
        )
        self.assertEqual(
            account_download_path(settings, settings.accounts[0]),
            Path("/statements/icici"),
        )

    def test_icici_variant_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(bank="icici", variant="amazon"),
                    self._account(bank="icici", variant="platinum", passwords=["y"]),
                    self._account(bank="icici", passwords=["z"]),
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"icici": self._icici_bank_config()},
            )
            settings = load_settings(app_config_path)
            amazon = settings.accounts[0]
            platinum = settings.accounts[1]
            catch_all = settings.accounts[2]
            self.assertEqual(
                amazon.subjects,
                ["Amazon Pay ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(
                platinum.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(platinum.variant, "platinum")
            self.assertEqual(
                catch_all.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )

    def test_unknown_variant_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici", variant="coral")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"icici": self._icici_bank_config()},
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.variant, "coral")
            self.assertEqual(
                account.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )

    def test_unknown_variant_user_bodies_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(
                        bank="icici",
                        variant="coral",
                        identifier="test2",
                        bodies=["XX1001"],
                        passwords=["test"],
                    )
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"icici": self._icici_bank_config()},
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.variant, "coral")
            self.assertEqual(
                account.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(account.bodies, ["XX1001"])

    def test_named_variant_partial_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici", variant="amazon")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "default": {
                            "subjects": ["ICICI default"],
                            "bodies": ["default body"],
                            "from": ["default.bank.com"],
                        },
                        "amazon": {"subjects": ["Amazon Pay ICICI"]},
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.subjects, ["Amazon Pay ICICI"])
            self.assertEqual(account.bodies, ["default body"])
            self.assertEqual(account.from_filters, ["default.bank.com"])

    def test_bank_without_default_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "amazon": {"subjects": ["Amazon Pay ICICI"]},
                    }
                },
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_unknown_variant_with_default_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="icici", variant="missing")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"icici": self._icici_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(
                settings.accounts[0].subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(settings.accounts[0].variant, "missing")

    def test_variant_normalization(self) -> None:
        account = UserAccountConfig.model_validate(
            {
                "bank": "hdfc",
                "variant": "Swiggy",
                "identifier": "1234",
                "passwords": ["x"],
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
            identifier="5678",
            subjects=["Amazon"],
        )
        self.assertEqual(account_label(with_variant), "icici/amazon")
        self.assertEqual(account_label(without_variant), "icici")

    def test_missing_source_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "download_path": ".",
                    "accounts": [self._account(bank="bob")],
                },
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_mbox_config_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob")],
                extra={"mbox": None},
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_explicit_thunderbird_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            _ = profile.mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob")],
                source={
                    "type": "thunderbird",
                    "thunderbird": {"profile": str(profile)},
                },
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            assert isinstance(settings.source, ThunderbirdSource)
            self.assertEqual(settings.source.thunderbird.profile, profile.resolve())

    def test_email_source_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob")],
                source={
                    "type": "email",
                    "email": {
                        "host": "imap.gmail.com",
                        "username": "user@gmail.com",
                        "password": "secret",
                        "folder": "[Gmail]/All Mail",
                    },
                },
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            assert isinstance(settings.source, EmailSource)
            self.assertEqual(settings.source.email.host, "imap.gmail.com")
            self.assertEqual(settings.source.email.folder, "[Gmail]/All Mail")

    def test_password_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [{"bank": "bob", "password": "legacy"}],
                },
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(SystemExit):
                _ = load_settings(app_config_path)

    def test_merge_settings_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = self._write_user_config(
                root,
                accounts=[self._account(bank="bob", passwords=["secret"])],
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {"bob": self._bob_bank_config()},
            )
            app_config = load_app_config(app_config_path)
            user_config = load_user_config(user_config_path)
            settings = merge_settings(app_config, user_config)
            self.assertEqual(settings.accounts[0].subjects, ["BOB"])
            self.assertEqual(settings.accounts[0].passwords, ["secret"])

    def test_alerts_config_optional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = self._write_user_config(
                root,
                accounts=[self._account(bank="bob")],
            )
            user_config = load_user_config(user_config_path)
            self.assertIsNone(user_config.alerts)

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
                    "email": _complete_email_alert_settings().model_dump(),
                }
            )

    def test_alerts_config_merged_into_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [self._account(bank="bob")],
                    "alerts": {
                        "type": "email",
                        "email": {
                            "smtp_host": "smtp.example.com",
                            "smtp_port": 587,
                            "username": "user@example.com",
                            "password": "secret",
                            "from_address": "user@example.com",
                            "to": ["alerts@example.com"],
                        },
                    },
                },
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertIsNotNone(settings.alerts)
            assert settings.alerts is not None
            self.assertEqual(settings.alerts.type, "email")
            assert isinstance(settings.alerts, EmailAlertsSettings)
            self.assertEqual(settings.alerts.email.smtp_host, "smtp.example.com")

    def test_resolve_config_path_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_config_path(None), DEFAULT_CONFIG_PATH.resolve())

    def test_resolve_config_path_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.config.json"
            _ = custom.write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {CONFIG_ENV_VAR: str(custom)}, clear=True):
                self.assertEqual(resolve_config_path(None), custom.resolve())

    def test_resolve_config_path_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.config.json"
            _ = custom.write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {CONFIG_ENV_VAR: "/other/app.config.json"}, clear=True):
                self.assertEqual(resolve_config_path(custom), custom.resolve())

    def test_local_app_config_overlay_inherits_banks_from_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": self._bob_bank_config(),
                    "icici": self._icici_bank_config(),
                },
            )
            overlay_path = self._write_app_config_overlay(
                root,
                {
                    "user_config": "/custom/user.config.json",
                },
            )

            app_config = load_app_config(overlay_path)

            self.assertEqual(app_config.user_config, Path("/custom/user.config.json"))
            self.assertIn("bob", app_config.banks)
            self.assertIn("icici", app_config.banks)
            self.assertEqual(
                app_config.banks["bob"]["easy"].subjects,
                ["BOB CREDIT CARD"],
            )

    def test_local_app_config_overlay_deep_merges_bank_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            overlay_path = self._write_app_config_overlay(
                root,
                {
                    "banks": {
                        "bob": {
                            "easy": {
                                "subjects": ["BOB EASY override"],
                            }
                        }
                    }
                },
            )

            app_config = load_app_config(overlay_path)

            self.assertEqual(
                app_config.banks["bob"]["default"].subjects,
                ["BOB"],
            )
            self.assertEqual(
                app_config.banks["bob"]["easy"].subjects,
                ["BOB EASY override"],
            )

    def test_local_app_config_overlay_requires_base_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay_path = self._write_app_config_overlay(
                root,
                {"user_config": "user.config.json"},
            )
            with self.assertRaises(SystemExit):
                _ = load_app_config(overlay_path)

    def test_run_settings_rejects_variant_without_bank(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    download_path=".",
                    profile=".",
                    accounts=[self._account(bank="bob")],
                    run={"variant": "easy"},
                )
            )

    def test_run_settings_rejects_no_matching_account(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    download_path=".",
                    profile=".",
                    accounts=[self._account(bank="bob", variant="easy")],
                    run={"bank": "pnb", "variant": "platinum"},
                )
            )

    def test_run_settings_merged_into_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [self._account(bank="bob", variant="easy")],
                    "run": {
                        "bank": "bob",
                        "variant": "easy",
                        "fy": "FY23-2024",
                        "force_text_extract": True,
                        "create_combined_csv": True,
                    },
                },
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.run.bank, "bob")
            self.assertEqual(settings.run.variant, "easy")
            self.assertEqual(settings.run.fy, "FY23-2024")
            self.assertTrue(settings.run.force_text_extract)
            self.assertTrue(settings.run.create_combined_csv)

    def test_accounts_to_run_filters_by_bank_and_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "profile": ".",
                    "download_path": ".",
                    "accounts": [
                        self._account(bank="bob", variant="easy", identifier="1"),
                        self._account(bank="pnb", variant="platinum", identifier="2"),
                    ],
                    "run": {"bank": "bob", "variant": "easy"},
                },
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {
                    "bob": self._bob_bank_config(),
                    "pnb": {
                        "default": {"subjects": ["PNB default"]},
                        "platinum": {"subjects": ["PNB"]},
                    },
                },
            )
            settings = load_settings(app_config_path)
            selected = accounts_to_run(settings)
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].bank, "bob")
            self.assertEqual(selected[0].variant, "easy")

    def test_run_settings_model_defaults(self) -> None:
        run = RunSettings()
        self.assertIsNone(run.bank)
        self.assertFalse(run.force_text_extract)
        self.assertFalse(run.create_combined_csv)


if __name__ == "__main__":
    _ = unittest.main()
