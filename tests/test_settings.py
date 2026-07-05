"""Settings loading tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import cast
from unittest import mock

from pydantic import ValidationError

from networthcsv.errors import ConfigError
from networthcsv.settings import (
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
    EmailSource,
    MatchingFields,
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
    UserAccountConfig,
    UserConfig,
    VariantOverride,
    account_download_path,
    account_label,
    accounts_to_run,
    parse_opening_date,
    parse_closing_date,
    resolve_account_search_dates,
    validate_run_filter,
    CONFIG_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    load_app_config,
    load_settings,
    load_user_config,
    merge_settings,
    normalize_bank,
    normalize_body_contains,
    normalize_from,
    normalize_account_number,
    normalize_text_contains,
    normalize_variant,
    resolve_config_path,
)


_DEFAULT_PROFILE = Path("/profile")
_DEFAULT_DOWNLOAD_PATH = Path("/statements")


def _variant_subjects(entry: MatchingFields | VariantOverride) -> list[str]:
    if isinstance(entry, MatchingFields):
        return entry.mail.subjects
    if entry.mail is None or entry.mail.subjects is None:
        raise AssertionError("variant mail subjects required")
    return entry.mail.subjects


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
            "default": {"mail": {"subjects": ["BOB"]}},
            "easy": {"mail": {"subjects": ["BOB CREDIT CARD"]}},
        }

    def _icici_bank_config(self) -> dict[str, object]:
        return {
            "default": {
                "mail": {
                    "subjects": ["ICICI Bank Credit Card Statement for the period"]
                }
            },
            "amazon": {
                "mail": {
                    "subjects": [
                        "Amazon Pay ICICI Bank Credit Card Statement for the period"
                    ]
                }
            },
        }

    def _write_app_config(
        self,
        directory: Path,
        user_config: str,
        banks: dict[str, object],
    ) -> Path:
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

    def _thunderbird_source(
        self, profile: Path = _DEFAULT_PROFILE
    ) -> ThunderbirdSource:
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
        data: dict[str, object] = {
            "account_number": "1234",
            "statement": {"text_contains": "1234"},
            "passwords": ["x"],
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
        account_number: str = "1234",
        text_contains: list[str] | str = "1234",
        subjects: list[str] | None = None,
        body_contains: list[str] | None = None,
        from_addresses: list[str] | None = None,
        passwords: list[str] | None = None,
        trim_start: list[str] | None = None,
        trim_end: list[str] | None = None,
        drop_sections: list[str] | None = None,
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
                "mail": {
                    "subjects": subjects or ["BOB"],
                    "body_contains": body_contains or [],
                    "from": from_addresses or [],
                },
                "statement": {
                    "trim_start": trim_start or [],
                    "trim_end": trim_end or [],
                    "drop_sections": drop_sections or [],
                    "text_contains": statement_text_contains,
                },
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
            self.assertEqual(settings.accounts[0].mail.subjects, ["BOB"])
            self.assertEqual(settings.accounts[0].passwords, ["secret", "other"])
            self.assertEqual(settings.accounts[0].account_number, "1234")
            self.assertEqual(settings.accounts[0].statement.text_contains, ["1234"])
            self.assertEqual(settings.accounts[0].mail.body_contains, [])
            self.assertEqual(settings.accounts[0].mail.from_addresses, [])
            self.assertEqual(settings.accounts[0].account_type, "credit_card")

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
                        "default": {"mail": {"subjects": ["ICICI default"]}},
                        "amazon": {
                            "mail": {
                                "subjects": ["Amazon Pay ICICI"],
                                "body_contains": ["Amazon Pay ICICI Bank Credit Card"],
                                "from": ["icicibank.com"],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(
                account.mail.body_contains, ["Amazon Pay ICICI Bank Credit Card"]
            )
            self.assertEqual(account.mail.from_addresses, ["icicibank.com"])

    def test_user_override_bodies_and_from(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(
                        bank="icici",
                        variant="amazon",
                        mail={
                            "body_contains": ["custom body"],
                            "from": ["custom@bank.com"],
                        },
                    )
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "icici": {
                        "default": {"mail": {"subjects": ["ICICI default"]}},
                        "amazon": {
                            "mail": {
                                "subjects": ["Amazon Pay ICICI"],
                                "body_contains": ["app body"],
                                "from": ["icicibank.com"],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.mail.body_contains, ["custom body"])
            self.assertEqual(account.mail.from_addresses, ["custom@bank.com"])

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
                            "mail": {
                                "subjects": ["ICICI generic"],
                                "body_contains": ["Default body"],
                                "from": ["default.bank.com"],
                            },
                        },
                        "amazon": {
                            "mail": {
                                "subjects": ["Amazon Pay ICICI"],
                                "body_contains": ["Amazon body"],
                                "from": ["amazon.bank.com"],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.mail.subjects, ["ICICI generic"])
            self.assertEqual(account.mail.body_contains, ["Default body"])
            self.assertEqual(account.mail.from_addresses, ["default.bank.com"])

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

        self.assertEqual(normalize_body_contains(["A", "a", " B "]), ["A", "B"])
        self.assertEqual(normalize_body_contains(None), [])
        self.assertEqual(normalize_body_contains(""), [])

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

    def test_load_with_opening_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(bank="bob", opening_date="04-2023"),
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.accounts[0].opening_date, date(2023, 4, 1))

    def test_load_with_closing_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[
                    self._account(
                        bank="bob",
                        opening_date="04-2023",
                        closing_date="08-2024",
                    ),
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.accounts[0].closing_date, date(2024, 8, 1))

    def test_omitted_closing_date_means_account_open(self) -> None:
        account = UserAccountConfig.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "opening_date": "04-2023",
            }
        )
        self.assertIsNone(account.closing_date)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob", opening_date="04-2023")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertIsNone(settings.accounts[0].closing_date)

    def test_closing_date_before_opening_date_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "08-2024",
                    "closing_date": "04-2023",
                }
            )

    def test_resolve_account_search_dates_uses_later_start(self) -> None:
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
        start, end = resolve_account_search_dates(account, date(2022, 1, 1))
        self.assertEqual(start, date(2023, 4, 1))
        self.assertEqual(end, date(2024, 9, 1))

        start, end = resolve_account_search_dates(account, date(2024, 1, 1))
        self.assertEqual(start, date(2024, 1, 1))
        self.assertEqual(end, date(2024, 9, 1))

    def test_resolve_account_search_dates_includes_month_after_closing(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "mail": {"subjects": ["stmt"]},
                "closing_date": date(2024, 2, 1),
            }
        )
        _start, end = resolve_account_search_dates(account, None)
        self.assertEqual(end, date(2024, 3, 1))

    def test_invalid_opening_date_format(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_opening_date("2023-04")
        with self.assertRaises(ValueError):
            _ = parse_opening_date("13-2023")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "opening_date": "2023-04",
                }
            )

    def test_invalid_closing_date_format(self) -> None:
        with self.assertRaises(ValueError):
            _ = parse_closing_date("2024-08")
        with self.assertRaises(ValidationError):
            _ = UserAccountConfig.model_validate(
                {
                    "bank": "bob",
                    "account_number": "1234",
                    "passwords": ["x"],
                    "closing_date": "2024-08",
                }
            )

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
                        "default": {"mail": {"subjects": ["PNB default"]}},
                        "platinum": {
                            "mail": {"subjects": ["PNB statement"]},
                            "statement": {
                                "trim_start": ["Transaction Date"],
                                "trim_end": ["End of Statement"],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.statement.trim_start, ["Transaction Date"])
            self.assertEqual(account.statement.trim_end, ["End of Statement"])

    def test_drop_sections_from_variant_defaults(self) -> None:
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
                        "default": {"mail": {"subjects": ["PNB default"]}},
                        "platinum": {
                            "mail": {"subjects": ["PNB statement"]},
                            "statement": {
                                "drop_sections": [
                                    "TAD for the month consists of current month purchases"
                                ],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(
                settings.accounts[0].statement.drop_sections,
                ["TAD for the month consists of current month purchases"],
            )

    def test_statement_date_from_variant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="idfc", variant="wow")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "idfc": {
                        "default": {"mail": {"subjects": ["Credit Card Statement"]}},
                        "wow": {
                            "mail": {"subjects": ["FIRST WOW! Credit Card Statement"]},
                            "metadata": {
                                "statement_date": [
                                    {"mode": "label_single", "label": "Statement Date"},
                                    {
                                        "mode": "top_range",
                                        "joiner": " - ",
                                        "take": "end",
                                        "search_chars": 500,
                                    },
                                ],
                            },
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            markers = settings.accounts[0].metadata.statement_date
            self.assertEqual(len(markers), 2)
            self.assertEqual(markers[0].mode, "label_single")
            self.assertEqual(markers[1].mode, "top_range")

    def test_balances_from_variant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob", variant="easy")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {
                            "mail": {"subjects": ["BOB"]},
                            "metadata": {
                                "balances": {
                                    "opening": [
                                        {
                                            "mode": "summary_table_column",
                                            "context": "Account Summary",
                                            "column": "Opening Balance",
                                        }
                                    ],
                                    "closing": [
                                        {
                                            "mode": "summary_table_column",
                                            "context": "Account Summary",
                                            "column": "Closing Balance",
                                        }
                                    ],
                                },
                            },
                        },
                        "easy": {"mail": {"subjects": ["BOB EASY"]}},
                    }
                },
            )
            settings = load_settings(app_config_path)
            markers = settings.accounts[0].metadata.balances
            self.assertEqual(len(markers.opening), 1)
            self.assertEqual(markers.opening[0].mode, "summary_table_column")
            self.assertEqual(len(markers.closing), 1)

    def test_invalid_statement_date_marker_rejected(self) -> None:
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
                {
                    "bob": {
                        "default": {
                            "mail": {"subjects": ["BOB"]},
                            "metadata": {
                                "statement_date": [
                                    {"mode": "unknown_mode", "label": "x"}
                                ],
                            },
                        }
                    }
                },
            )
            with self.assertRaises(ConfigError):
                _ = load_settings(app_config_path)

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
                        mail={"subjects": ["Custom BOB subject for testing"]},
                    )
                ],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {"mail": {"subjects": ["E-statement for your BOB"]}}
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(
                settings.accounts[0].mail.subjects,
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
            with self.assertRaises(ConfigError):
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
            self.assertEqual(
                app_config.user_config, (root / "user.config.json").resolve()
            )

    def test_missing_account_number_rejected(self) -> None:
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
            with self.assertRaises(ConfigError):
                _ = load_settings(app_config_path)

    def test_duplicate_account_number_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    accounts=[
                        self._account(bank="bob"),
                        self._account(bank="icici", passwords=["y"]),
                    ],
                )
            )

    def test_same_bank_variant_different_account_numbers_allowed(self) -> None:
        user = UserConfig.model_validate(
            self._user_config_payload(
                accounts=[
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
        )
        self.assertEqual(len(user.accounts), 2)

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
            account_download_path(settings, settings.accounts[0]),
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
            account_download_path(settings, settings.accounts[0]),
            Path("/statements/bank_account/1234"),
        )

    def test_icici_variant_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
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
                amazon.mail.subjects,
                ["Amazon Pay ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(
                platinum.mail.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(platinum.variant, "platinum")
            self.assertEqual(
                catch_all.mail.subjects,
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
                account.mail.subjects,
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
                        account_number="test2",
                        mail={"body_contains": ["XX1001"]},
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
                account.mail.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(account.mail.body_contains, ["XX1001"])

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
                            "mail": {
                                "subjects": ["ICICI default"],
                                "body_contains": ["default body"],
                                "from": ["default.bank.com"],
                            },
                        },
                        "amazon": {"mail": {"subjects": ["Amazon Pay ICICI"]}},
                    }
                },
            )
            settings = load_settings(app_config_path)
            account = settings.accounts[0]
            self.assertEqual(account.mail.subjects, ["Amazon Pay ICICI"])
            self.assertEqual(account.mail.body_contains, ["default body"])
            self.assertEqual(account.mail.from_addresses, ["default.bank.com"])

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
                        "amazon": {"mail": {"subjects": ["Amazon Pay ICICI"]}},
                    }
                },
            )
            with self.assertRaises(ConfigError):
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
                settings.accounts[0].mail.subjects,
                ["ICICI Bank Credit Card Statement for the period"],
            )
            self.assertEqual(settings.accounts[0].variant, "missing")

    def test_variant_normalization(self) -> None:
        account = UserAccountConfig.model_validate(
            {
                "bank": "hdfc",
                "variant": "Swiggy",
                "account_number": "1234",
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
            account_number="5678",
            subjects=["Amazon"],
        )
        self.assertEqual(account_label(with_variant), "icici/amazon (1234)")
        self.assertEqual(account_label(without_variant), "icici (5678)")

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
            with self.assertRaises(ConfigError):
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
                    "source": {
                        "type": "thunderbird",
                        "thunderbird": {"profile": "."},
                    },
                    "download_path": ".",
                    "accounts": [{"bank": "bob", "password": "legacy"}],
                },
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {"bob": self._bob_bank_config()},
            )
            with self.assertRaises(ConfigError):
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
            self.assertEqual(settings.accounts[0].mail.subjects, ["BOB"])
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
                    "source": {
                        "type": "thunderbird",
                        "thunderbird": {"profile": "."},
                    },
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
            with mock.patch.dict(
                os.environ, {CONFIG_ENV_VAR: "/other/app.config.json"}, clear=True
            ):
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
                _variant_subjects(app_config.banks["bob"]["easy"]),
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
                                "mail": {
                                    "subjects": ["BOB EASY override"],
                                }
                            }
                        }
                    }
                },
            )

            app_config = load_app_config(overlay_path)

            self.assertEqual(
                _variant_subjects(app_config.banks["bob"]["default"]),
                ["BOB"],
            )
            self.assertEqual(
                _variant_subjects(app_config.banks["bob"]["easy"]),
                ["BOB EASY override"],
            )

    def test_local_app_config_overlay_requires_base_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay_path = self._write_app_config_overlay(
                root,
                {"user_config": "user.config.json"},
            )
            with self.assertRaises(ConfigError):
                _ = load_app_config(overlay_path)

    def test_run_settings_rejects_no_matching_account(self) -> None:
        with self.assertRaises(ValidationError):
            _ = UserConfig.model_validate(
                self._user_config_payload(
                    download_path=".",
                    profile=".",
                    accounts=[self._account(bank="bob", variant="easy")],
                    run={"identifier": "missing"},
                )
            )

    def test_run_settings_merged_into_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "source": {
                        "type": "thunderbird",
                        "thunderbird": {"profile": "."},
                    },
                    "download_path": ".",
                    "accounts": [
                        self._account(bank="bob", variant="easy", account_number="5678")
                    ],
                    "run": {
                        "identifier": "5678",
                        "financial_year": "FY23-2024",
                    },
                },
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {"bob": self._bob_bank_config()},
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.run.identifier, "5678")
            self.assertEqual(settings.run.financial_year, "FY23-2024")

    def test_accounts_to_run_filters_by_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_config_path = root / "user.config.json"
            self._write_json(
                user_config_path,
                {
                    "source": {
                        "type": "thunderbird",
                        "thunderbird": {"profile": "."},
                    },
                    "download_path": ".",
                    "accounts": [
                        self._account(bank="bob", variant="easy", account_number="1"),
                        self._account(
                            bank="pnb", variant="platinum", account_number="2"
                        ),
                    ],
                    "run": {"identifier": "1"},
                },
            )
            app_config_path = self._write_app_config(
                root,
                str(user_config_path.name),
                {
                    "bob": self._bob_bank_config(),
                    "pnb": {
                        "default": {"mail": {"subjects": ["PNB default"]}},
                        "platinum": {"mail": {"subjects": ["PNB"]}},
                    },
                },
            )
            settings = load_settings(app_config_path)
            selected = accounts_to_run(settings)
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
            validate_run_filter(settings)

    def test_run_settings_model_defaults(self) -> None:
        run = RunSettings()
        self.assertIsNone(run.identifier)
        self.assertIsNone(run.financial_year)

    def test_account_type_defaults_to_credit_card(self) -> None:
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
            settings = load_settings(app_config_path)
            self.assertEqual(settings.accounts[0].account_type, "credit_card")

    def test_account_type_inherited_from_default_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob", variant="easy")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {
                            "type": "bank_account",
                            "mail": {"subjects": ["BOB default"]},
                        },
                        "easy": {"mail": {"subjects": ["BOB EASY"]}},
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.accounts[0].account_type, "bank_account")

    def test_account_type_explicit_on_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ = (root / "profile").mkdir()
            _ = (root / "statements").mkdir()
            _ = self._write_user_config(
                root,
                accounts=[self._account(bank="bob", variant="savings")],
            )
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {"mail": {"subjects": ["BOB default"]}},
                        "savings": {
                            "type": "bank_account",
                            "mail": {"subjects": ["BOB savings"]},
                        },
                    }
                },
            )
            settings = load_settings(app_config_path)
            self.assertEqual(settings.accounts[0].account_type, "bank_account")

    def test_invalid_account_type_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_config_path = self._write_app_config(
                root,
                "user.config.json",
                {
                    "bob": {
                        "default": {
                            "type": "wallet",
                            "subjects": ["BOB"],
                        }
                    }
                },
            )
            with self.assertRaises(ConfigError):
                _ = load_app_config(app_config_path)


if __name__ == "__main__":
    _ = unittest.main()
