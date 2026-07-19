"""Pydantic config models for accounts.json and environment settings."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, ClassVar, Literal

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
    model_validator,
)


def _require_opening_date(value: object) -> date:
    parsed = parse_opening_date(value)
    if parsed is None:
        raise ValueError("opening_date is required")
    return parsed


OpeningDate = Annotated[date, BeforeValidator(_require_opening_date)]
ClosingDate = Annotated[date | None, BeforeValidator(parse_closing_date)]


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


def reject_duplicate_accounts(accounts: list[UserAccountConfig]) -> None:
    seen_keys: set[tuple[str, str | None, str]] = set()
    numbers_by_bank: dict[str, set[str]] = {}
    for index, account in enumerate(accounts):
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


def parse_accounts_config(
    data: list[object],
    *,
    allow_empty: bool = False,
) -> list[UserAccountConfig]:
    if not data:
        if allow_empty:
            return []
        raise ValueError("accounts config must contain at least one account")
    accounts = [UserAccountConfig.model_validate(item) for item in data]
    reject_duplicate_accounts(accounts)
    return accounts


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
