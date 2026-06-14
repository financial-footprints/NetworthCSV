"""Load settings from extractor.config.json."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "extractor.config.json"
ENV_CONFIG_VAR = "CCPARSER_CONFIG"


class AccountSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    bank: str
    subjects: list[str] = Field(min_length=1)
    passwords: list[str] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_subject(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data: dict[str, object] = cast(dict[str, object], value)
        if "subject" in data and "subjects" in data:
            raise ValueError("use either subject or subjects, not both")
        if "subject" in data:
            migrated = dict(data)
            migrated["subjects"] = migrated.pop("subject")
            return migrated
        return data

    @field_validator("bank", mode="before")
    @classmethod
    def normalize_bank(cls, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("bank is required")
        segments = [segment.strip().lower() for segment in raw.split("/") if segment.strip()]
        if not segments:
            raise ValueError("bank is required")
        return "/".join(segments)

    @field_validator("subjects", mode="before")
    @classmethod
    def normalize_subjects(cls, value: object) -> list[str]:
        if isinstance(value, str):
            items: list[object] = [value]
        elif isinstance(value, list):
            items = cast(list[object], value)
        else:
            raise ValueError("subjects must be a string or a non-empty array")
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            subject = str(item).strip()
            if subject and subject.lower() not in seen:
                seen.add(subject.lower())
                unique.append(subject)
        if not unique:
            raise ValueError("subjects must contain at least one non-empty value")
        return unique

    @field_validator("passwords", mode="before")
    @classmethod
    def normalize_passwords(cls, value: object) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("passwords must be a non-empty array")
        items: list[object] = cast(list[object], value)
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            password = str(item).strip()
            if password and password not in seen:
                seen.add(password)
                unique.append(password)
        if not unique:
            raise ValueError("passwords must contain at least one non-empty value")
        return unique


class Settings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    profile: Path
    download_path: Path
    start_date: date | None = None
    mbox: Path | None = None
    accounts: list[AccountSettings] = Field(min_length=1)
    create_combined_csv: bool = False

    @field_validator("start_date", mode="before")
    @classmethod
    def parse_start_date(cls, value: object) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("start_date must be an ISO date string or null")
        stripped = value.strip()
        if not stripped:
            return None
        return date.fromisoformat(stripped)

    @classmethod
    def _resolve_path(cls, value: object, base: Path) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = (base / path).resolve()
        return path

    @classmethod
    def from_json(cls, data: dict[str, object], *, config_path: Path) -> Settings:
        base = config_path.parent
        profile_raw = data.get("profile")
        download_raw = data.get("download_path")
        if not profile_raw:
            raise ValueError("profile is required")
        if not download_raw:
            raise ValueError("download_path is required")

        mbox_raw = data.get("mbox")
        return cls.model_validate(
            {
                "profile": cls._resolve_path(profile_raw, base),
                "download_path": cls._resolve_path(download_raw, base),
                "start_date": data.get("start_date"),
                "mbox": cls._resolve_path(mbox_raw, base) if mbox_raw else None,
                "accounts": data.get("accounts", []),
                "create_combined_csv": bool(data.get("create_combined_csv", False)),
            }
        )


def account_download_path(settings: Settings, account: AccountSettings) -> Path:
    return settings.download_path / account.bank


def parser_bank(account: AccountSettings) -> str:
    return account.bank.split("/")[0]


def account_txt_path(settings: Settings, account: AccountSettings) -> Path:
    return account_download_path(settings, account) / "txt"


def find_account(settings: Settings, download_dir: Path) -> AccountSettings | None:
    resolved = download_dir.expanduser().resolve()
    for account in settings.accounts:
        if account_download_path(settings, account).resolve() == resolved:
            return account
    return None


def account_for_download_dir(settings: Settings, download_dir: Path) -> AccountSettings:
    account = find_account(settings, download_dir)
    if account is None:
        known = ", ".join(str(account_download_path(settings, a)) for a in settings.accounts)
        raise SystemExit(
            f"error: {download_dir} does not match any account download path (known: {known})"
        )
    return account


def resolve_config_path(override: str | Path | None = None) -> Path:
    """Resolve config path: CLI override, then $CCPARSER_CONFIG, then default."""
    if override is not None:
        value = str(override).strip()
        if value:
            return Path(value).expanduser().resolve()

    env_value = os.environ.get(ENV_CONFIG_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return DEFAULT_CONFIG_PATH.resolve()


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_config = resolve_config_path(config_path)
    if not resolved_config.is_file():
        raise SystemExit(f"error: config not found: {resolved_config}")

    with resolved_config.open(encoding="utf-8") as fh:
        loaded = cast(object, json.load(fh))
    if not isinstance(loaded, dict):
        raise SystemExit(f"error: config must be a JSON object: {resolved_config}")

    try:
        return Settings.from_json(cast(dict[str, object], loaded), config_path=resolved_config)
    except (ValidationError, ValueError, TypeError) as exc:
        raise SystemExit(f"error: invalid config {resolved_config}: {exc}") from exc
