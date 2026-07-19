"""Pydantic config models for app.config.json and user.config.json."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, ClassVar, Literal, cast

from networthcsv.logging import LogLevel
from networthcsv.settings._load import resolve_path
from networthcsv.settings._validators import (
    AccountNumber,
    BankName,
    Marker,
    OptionalIdentifier,
    Passwords,
    VariantName,
    _require_field,
    normalize_alert_recipients,
)
from networthcsv.utils.account_dates import (
    parse_account_date,
    parse_closing_date,
    parse_opening_date,
)
from networthcsv.utils.banks.account_matching import (
    MatchingFields,
    MatchingFieldsCore,
    MailMatchOverride,
    StatementCleanupOverride,
)
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _require_opening_date(value: object) -> date:
    parsed = parse_opening_date(value)
    if parsed is None:
        raise ValueError("opening_date is required")
    return parsed


OpeningDate = Annotated[date, BeforeValidator(_require_opening_date)]
ClosingDate = Annotated[date | None, BeforeValidator(parse_closing_date)]


class AppConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    user_config: Path

    @field_validator("user_config", mode="before")
    @classmethod
    def validate_user_config(cls, value: object) -> object:
        if value is None or str(value).strip() == "":
            raise ValueError("user_config is required")
        return value

    @classmethod
    def from_json(cls, data: dict[str, object], *, config_path: Path) -> AppConfig:
        base = config_path.parent
        return cls.model_validate(
            {
                "user_config": resolve_path(data["user_config"], base)
                if data.get("user_config")
                else None,
            }
        )


class UserAccountConfig(MatchingFieldsCore):
    bank: BankName
    variant: VariantName = None
    account_number: AccountNumber
    passwords: Passwords
    opening_date: OpeningDate
    closing_date: ClosingDate = None
    mail: MailMatchOverride | None = None
    statement: StatementCleanupOverride | None = None

    @model_validator(mode="after")
    def validate_account_date_range(self) -> UserAccountConfig:
        if self.closing_date is None:
            return self
        if self.closing_date < self.opening_date:
            raise ValueError("closing_date must be on or after opening_date")
        return self


class EmailAlertSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    smtp_host: Annotated[str, BeforeValidator(_require_field("smtp_host"))]
    smtp_port: int
    use_tls: bool = True
    username: Annotated[str, BeforeValidator(_require_field("username"))]
    password: Annotated[str, BeforeValidator(_require_field("password"))]
    from_address: Annotated[str, BeforeValidator(_require_field("from_address"))]
    to: Annotated[list[str], BeforeValidator(normalize_alert_recipients)]


class ConsoleAlertSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    type: Literal["console"] = "console"


class EmailAlertsSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    type: Literal["email"] = "email"
    email: EmailAlertSettings


AlertSettings = Annotated[
    ConsoleAlertSettings | EmailAlertsSettings,
    Field(discriminator="type"),
]


class RunSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    identifier: OptionalIdentifier = None
    financial_year: Marker = None


class EmailSourceSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    host: Annotated[str, BeforeValidator(_require_field("host"))]
    port: int = 993
    username: Annotated[str, BeforeValidator(_require_field("username"))]
    password: Annotated[str, BeforeValidator(_require_field("password"))]
    folder: str = "INBOX"
    use_ssl: bool = True


class ThunderbirdSourceSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    profile: Path


class ThunderbirdSource(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    type: Literal["thunderbird"] = "thunderbird"
    thunderbird: ThunderbirdSourceSettings


class EmailSource(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    type: Literal["email"] = "email"
    email: EmailSourceSettings


SourceSettings = Annotated[
    ThunderbirdSource | EmailSource,
    Field(discriminator="type"),
]


def _resolve_source(raw: object, base: Path) -> ThunderbirdSource | EmailSource:
    if not isinstance(raw, dict):
        raise ValueError("source must be an object")
    data = dict(cast(dict[str, object], raw))
    source_type = data.get("type")
    if source_type == "thunderbird":
        thunderbird_raw = data.get("thunderbird")
        if isinstance(thunderbird_raw, dict):
            thunderbird = dict(cast(dict[str, object], thunderbird_raw))
            profile = thunderbird.get("profile")
            if profile:
                thunderbird["profile"] = resolve_path(profile, base)
            data["thunderbird"] = thunderbird
        return ThunderbirdSource.model_validate(data)
    if source_type == "email":
        return EmailSource.model_validate(data)
    raise ValueError("source.type must be 'thunderbird' or 'email'")


def _prepare_user_config_data(data: dict[str, object], base: Path) -> dict[str, object]:
    prepared = dict(data)
    source_raw = data.get("source")
    if source_raw is not None:
        prepared["source"] = _resolve_source(source_raw, base)
    download_raw = data.get("download_path")
    if download_raw:
        prepared["download_path"] = resolve_path(download_raw, base)
    accounts_raw = data.get("accounts")
    if isinstance(accounts_raw, list):
        prepared["accounts"] = list(accounts_raw)
    return prepared


def _user_account_matches_run_filter(
    account: UserAccountConfig, run: RunSettings
) -> bool:
    if run.identifier is None:
        return True
    return account.account_number == run.identifier


class UserConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    source: SourceSettings
    download_path: Path
    log_level: LogLevel = "info"
    start_date: date | None = None
    accounts: list[UserAccountConfig] = Field(min_length=1)
    alerts: AlertSettings | None = None
    run: RunSettings | None = None

    @field_validator("download_path", mode="before")
    @classmethod
    def validate_download_path(cls, value: object) -> object:
        if value is None or str(value).strip() == "":
            raise ValueError("download_path is required")
        return value

    @model_validator(mode="after")
    def validate_run_filter(self) -> UserConfig:
        if self.run is None or self.run.identifier is None:
            return self
        matches = [
            account
            for account in self.accounts
            if _user_account_matches_run_filter(account, self.run)
        ]
        if not matches:
            known = ", ".join(account.account_number for account in self.accounts)
            raise ValueError(f"run filter matches no account (known: {known})")
        return self

    @model_validator(mode="after")
    def reject_duplicate_accounts(self) -> UserConfig:
        seen_keys: set[tuple[str, str | None, str]] = set()
        numbers_by_bank: dict[str, set[str]] = {}
        for index, account in enumerate(self.accounts):
            key = (account.bank, account.variant, account.account_number)
            if key in seen_keys:
                raise ValueError(
                    f"accounts[{index}] ({account.account_number}): duplicate account"
                )
            seen_keys.add(key)

            banks_for_number = numbers_by_bank.setdefault(account.account_number, set())
            if banks_for_number and account.bank not in banks_for_number:
                raise ValueError(
                    f"accounts[{index}] ({account.account_number}): duplicate account"
                )
            banks_for_number.add(account.bank)
        return self

    @field_validator("start_date", mode="before")
    @classmethod
    def parse_start_date(cls, value: object) -> date | None:
        return parse_account_date(value, "start_date")

    @classmethod
    def from_json(cls, data: dict[str, object], *, config_path: Path) -> UserConfig:
        return cls.model_validate(_prepare_user_config_data(data, config_path.parent))


class ResolvedAccount(MatchingFields):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", populate_by_name=True, frozen=True
    )

    bank: str
    variant: str | None = None
    account_number: str
    passwords: list[str] = Field(min_length=1)
    opening_date: OpeningDate
    closing_date: ClosingDate = None
