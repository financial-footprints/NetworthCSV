"""Load settings from app.config.json and user.config.json."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, ClassVar, Literal, cast

from networthcsv.errors import ConfigError
from networthcsv.logging import LogLevel

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "app.config.json"
BASE_APP_CONFIG_FILENAME = "app.config.json"
LOCAL_APP_CONFIG_FILENAME = "app.config.local.json"
CONFIG_ENV_VAR = "NETWORTHCSV_CONFIG"

DEFAULT_BALANCE_MATCH_TOLERANCE = Decimal("0.21")


def normalize_bank(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("bank is required")
    if "/" in raw or "\\" in raw:
        raise ValueError("bank must not contain path separators")
    return raw


def normalize_account_type(value: object) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if not raw:
        return "credit_card"
    if raw not in ("bank_account", "credit_card"):
        raise ValueError("type must be bank_account or credit_card")
    return raw


def _optional_account_type(value: object) -> str | None:
    if value is None or value == "":
        return None
    return normalize_account_type(value)


def normalize_variant(value: object) -> str | None:
    if value is None or value == "":
        return None
    variant = str(value).strip().lower()
    if not variant:
        return None
    if "/" in variant or "\\" in variant:
        raise ValueError("variant must not contain path separators")
    return variant


def _normalize_from_entry(entry: str) -> str:
    if any(ch.isspace() for ch in entry):
        raise ValueError("from entries must not contain whitespace")
    if "@" in entry:
        local, sep, domain = entry.partition("@")
        if not local or not sep or not domain or "@" in domain:
            raise ValueError(f"invalid from email address: {entry!r}")
    return entry


def normalize_string_list(
    value: object,
    *,
    field_name: str,
    required: bool = False,
    allow_empty: bool = True,
    allow_scalar: bool = True,
    list_only: bool = False,
    case_insensitive_dedupe: bool = False,
    lowercase_items: bool = False,
    item_validator: Callable[[str], str] | None = None,
) -> list[str]:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} must contain at least one non-empty value")
        return []

    if list_only:
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field_name} must be a non-empty array")
        items = cast(list[object], value)
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        shape = "a non-empty array" if required else "a string or an array"
        raise ValueError(f"{field_name} must be {shape}")

    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if lowercase_items:
            text = text.lower()
        if item_validator is not None:
            text = item_validator(text)
        dedupe_key = text.lower() if case_insensitive_dedupe else text
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            unique.append(text)

    if required and not unique:
        raise ValueError(f"{field_name} must contain at least one non-empty value")
    if not allow_empty and not unique and value not in (None, ""):
        raise ValueError(f"{field_name} must contain at least one non-empty value")
    return unique


def normalize_subjects(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="subjects",
        required=True,
        allow_empty=False,
        case_insensitive_dedupe=True,
    )


def normalize_marker(value: object) -> str | None:
    if value is None or value == "":
        return None
    marker = str(value).strip()
    return marker or None


def normalize_body_contains(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="body_contains",
        case_insensitive_dedupe=True,
    )


def normalize_from(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="from",
        lowercase_items=True,
        item_validator=_normalize_from_entry,
    )


def normalize_account_number(value: object) -> str:
    account_number = str(value or "").strip()
    if not account_number:
        raise ValueError("account_number is required")
    return account_number


def normalize_text_contains(value: object) -> list[str]:
    return normalize_string_list(value, field_name="text_contains")


def normalize_passwords(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="passwords",
        required=True,
        allow_empty=False,
        list_only=True,
    )


def normalize_alert_recipients(value: object) -> list[str]:
    return normalize_string_list(
        value,
        field_name="to",
        required=True,
        allow_empty=False,
        case_insensitive_dedupe=True,
    )


def _optional(normalizer: Callable[[object], object]) -> Callable[[object], object]:
    def wrap(value: object) -> object:
        if value is None or value == "":
            return None
        return normalizer(value)

    return wrap


def _optional_bank(value: object) -> str | None:
    if value is None or value == "":
        return None
    return normalize_bank(value)


def _require_non_empty(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _require_field(field_name: str) -> Callable[[object], str]:
    def validate(value: object) -> str:
        return _require_non_empty(value, field_name=field_name)

    return validate


Subjects = Annotated[list[str], BeforeValidator(normalize_subjects)]
OptionalSubjects = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_subjects))
]
BodyContains = Annotated[list[str], BeforeValidator(normalize_body_contains)]
OptionalBodyContains = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_body_contains))
]
FromAddresses = Annotated[list[str], BeforeValidator(normalize_from)]
OptionalFromAddresses = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_from))
]
Marker = Annotated[str | None, BeforeValidator(normalize_marker)]
BankName = Annotated[str, BeforeValidator(normalize_bank)]
AccountTypeName = Annotated[str, BeforeValidator(normalize_account_type)]
OptionalAccountTypeName = Annotated[str | None, BeforeValidator(_optional_account_type)]
OptionalBankName = Annotated[str | None, BeforeValidator(_optional_bank)]
VariantName = Annotated[str | None, BeforeValidator(normalize_variant)]
AccountNumber = Annotated[str, BeforeValidator(normalize_account_number)]
OptionalIdentifier = Annotated[
    str | None, BeforeValidator(_optional(normalize_account_number))
]
TextContains = Annotated[list[str], BeforeValidator(normalize_text_contains)]
OptionalTextContains = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_text_contains))
]
Passwords = Annotated[list[str], BeforeValidator(normalize_passwords)]


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            parts.append(f"{loc}: {error['msg']}")
        return "; ".join(parts)
    return str(exc)


def _config_error(
    config_path: Path,
    exc: Exception,
    *,
    context: str = "",
) -> ConfigError:
    detail = _format_exception(exc)
    message = f"invalid config {config_path}"
    if context:
        message = f"{message} ({context})"
    return ConfigError(f"{message}: {detail}")


class MatchingFieldsCore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", populate_by_name=True
    )


class MailMatchConfig(MatchingFieldsCore):
    subjects: Subjects
    body_contains: BodyContains = []
    from_addresses: FromAddresses = Field(default_factory=list, alias="from")


class MailMatchOverride(MatchingFieldsCore):
    subjects: OptionalSubjects = None
    body_contains: OptionalBodyContains = None
    from_addresses: OptionalFromAddresses = Field(default=None, alias="from")


class StatementCleanupConfig(MatchingFieldsCore):
    text_contains: TextContains = []


class StatementCleanupOverride(MatchingFieldsCore):
    text_contains: OptionalTextContains = None


class MatchingFields(MatchingFieldsCore):
    account_type: AccountTypeName = Field(default="credit_card", alias="type")
    mail: MailMatchConfig
    statement: StatementCleanupConfig = Field(default_factory=StatementCleanupConfig)


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
                "user_config": _resolve_path(data["user_config"], base)
                if data.get("user_config")
                else None,
            }
        )


_ACCOUNT_DATE_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


def parse_account_date(value: object, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a DD-MM-YYYY string or null")
    stripped = value.strip()
    if not stripped:
        return None
    match = _ACCOUNT_DATE_PATTERN.fullmatch(stripped)
    if match is None:
        raise ValueError(f"{field_name} must be in DD-MM-YYYY format")
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    if month < 1 or month > 12:
        raise ValueError(f"{field_name} month must be between 01 and 12")
    if day < 1 or day > 31:
        raise ValueError(f"{field_name} day must be between 01 and 31")
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid calendar date") from exc


def parse_opening_date(value: object) -> date | None:
    return parse_account_date(value, "opening_date")


def parse_closing_date(value: object) -> date | None:
    return parse_account_date(value, "closing_date")


def format_account_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d-%m-%Y")


class UserAccountConfig(MatchingFieldsCore):
    bank: BankName
    variant: VariantName = None
    account_number: AccountNumber
    passwords: Passwords
    opening_date: date | None = None
    closing_date: date | None = None
    mail: MailMatchOverride | None = None
    statement: StatementCleanupOverride | None = None

    @field_validator("opening_date", mode="before")
    @classmethod
    def validate_opening_date(cls, value: object) -> date | None:
        return parse_opening_date(value)

    @field_validator("closing_date", mode="before")
    @classmethod
    def validate_closing_date(cls, value: object) -> date | None:
        return parse_closing_date(value)

    @model_validator(mode="after")
    def validate_account_date_range(self) -> UserAccountConfig:
        if self.opening_date is None or self.closing_date is None:
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
                thunderbird["profile"] = _resolve_path(profile, base)
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
        prepared["download_path"] = _resolve_path(download_raw, base)
    accounts_raw = data.get("accounts")
    if isinstance(accounts_raw, list):
        prepared["accounts"] = list(accounts_raw)
    return prepared


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
    opening_date: date | None = None
    closing_date: date | None = None

    @field_validator("opening_date", mode="before")
    @classmethod
    def validate_opening_date(cls, value: object) -> date | None:
        return parse_opening_date(value)

    @field_validator("closing_date", mode="before")
    @classmethod
    def validate_closing_date(cls, value: object) -> date | None:
        return parse_closing_date(value)


def resolve_account_search_dates(
    account: ResolvedAccount,
    global_start_date: date | None,
) -> tuple[date | None, date | None]:
    start_candidates: list[date] = []
    if global_start_date is not None:
        start_candidates.append(global_start_date)
    if account.opening_date is not None:
        start_candidates.append(account.opening_date)
    effective_start = max(start_candidates) if start_candidates else None
    effective_end = (
        exclusive_search_end_date(account.closing_date)
        if account.closing_date is not None
        else None
    )
    return effective_start, effective_end


def exclusive_search_end_date(end_date: date) -> date:
    """Return the day after ``end_date`` for an exclusive IMAP/Gmail ``BEFORE`` bound."""
    return end_date + timedelta(days=1)


@dataclass(frozen=True)
class Settings:
    source: ThunderbirdSource | EmailSource
    download_path: Path
    accounts: list[ResolvedAccount]
    alerts: ConsoleAlertSettings | EmailAlertsSettings | None
    run: RunSettings
    log_level: LogLevel = "info"
    start_date: date | None = None


def _merge_model_fields(
    base: BaseModel, overlay: BaseModel | None
) -> dict[str, object]:
    merged = cast(dict[str, object], base.model_dump(by_alias=True))
    if overlay is None:
        return merged
    overlay_dump = cast(
        dict[str, object], overlay.model_dump(exclude_none=True, by_alias=True)
    )
    merged.update(overlay_dump)
    return merged


def _merge_mail(
    base: MailMatchConfig, overlay: MailMatchOverride | None
) -> MailMatchConfig:
    if overlay is None:
        return base
    return MailMatchConfig.model_validate(_merge_model_fields(base, overlay))


def _merge_statement(
    base: StatementCleanupConfig, overlay: StatementCleanupOverride | None
) -> StatementCleanupConfig:
    if overlay is None:
        return base
    return StatementCleanupConfig.model_validate(_merge_model_fields(base, overlay))


class _MatchingOverlay(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    account_type: OptionalAccountTypeName = Field(default=None, alias="type")
    mail: MailMatchOverride | None = None
    statement: StatementCleanupOverride | None = None


def _matching_overlay_from(model: BaseModel) -> _MatchingOverlay:
    dumped = cast(dict[str, object], model.model_dump(exclude_none=True, by_alias=True))
    overlay_data = {
        key: dumped[key] for key in ("type", "mail", "statement") if key in dumped
    }
    return _MatchingOverlay.model_validate(overlay_data)


def merge_matching(base: MatchingFields, *overlays: BaseModel) -> MatchingFields:
    mail = base.mail
    statement = base.statement
    account_type = base.account_type
    for overlay in overlays:
        parsed = _matching_overlay_from(overlay)
        if parsed.account_type is not None:
            account_type = parsed.account_type
        mail = _merge_mail(mail, parsed.mail)
        statement = _merge_statement(statement, parsed.statement)
    return MatchingFields.model_validate(
        {
            "type": account_type,
            "mail": mail.model_dump(by_alias=True),
            "statement": statement.model_dump(by_alias=True),
        }
    )


def _known_bank_names() -> str:
    from networthcsv.utils.banks import list_handlers

    banks = sorted({key.split("/")[0] for key in list_handlers()})
    return ", ".join(banks)


def _resolved_account(
    user_account: UserAccountConfig, defaults: MatchingFields, *, bank_key: str
) -> ResolvedAccount:
    matching = merge_matching(defaults, user_account)
    return ResolvedAccount.model_validate(
        {
            "bank": bank_key,
            "variant": user_account.variant,
            "account_number": user_account.account_number,
            "passwords": user_account.passwords,
            "opening_date": user_account.opening_date,
            "closing_date": user_account.closing_date,
            **matching.model_dump(),
        }
    )


def _user_account_matches_run_filter(
    account: UserAccountConfig, run: RunSettings
) -> bool:
    if run.identifier is None:
        return True
    return account.account_number == run.identifier


def _account_matches_run_filter(account: ResolvedAccount, run: RunSettings) -> bool:
    if run.identifier is None:
        return True
    return account.account_number == run.identifier


def _validate_run_filter(
    run: RunSettings,
    accounts: Sequence[ResolvedAccount],
) -> None:
    if run.identifier is None:
        return
    matches = [
        account for account in accounts if _account_matches_run_filter(account, run)
    ]
    if not matches:
        known = ", ".join(account.account_number for account in accounts)
        raise ValueError(f"run filter matches no account (known: {known})")


def merge_settings(app: AppConfig, user: UserConfig) -> Settings:
    from networthcsv.utils.banks import get_handler

    accounts: list[ResolvedAccount] = []
    for index, user_account in enumerate(user.accounts):
        bank_key = user_account.bank
        label = account_label_from_parts(bank_key, user_account.variant)
        context = f"accounts[{index}] ({label})"
        try:
            defaults = get_handler(bank_key, user_account.variant).matching_defaults()
            accounts.append(
                _resolved_account(user_account, defaults, bank_key=bank_key)
            )
        except KeyError as exc:
            known = _known_bank_names()
            raise ValueError(
                f"{context}: bank {bank_key!r} is not defined (known: {known})"
            ) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError(f"{context}: {exc}") from exc

    settings = Settings(
        source=user.source,
        download_path=user.download_path,
        log_level=user.log_level,
        start_date=user.start_date,
        accounts=accounts,
        alerts=user.alerts,
        run=user.run or RunSettings(),
    )
    _validate_run_filter(settings.run, settings.accounts)
    return settings


def accounts_to_run(settings: Settings) -> list[ResolvedAccount]:
    run = settings.run
    if run.identifier is None:
        return list(settings.accounts)
    return [
        account
        for account in settings.accounts
        if _account_matches_run_filter(account, run)
    ]


def validate_run_filter(settings: Settings) -> None:
    """Validate run filter against resolved accounts (e.g. after CLI overrides)."""
    _validate_run_filter(settings.run, settings.accounts)


def account_label_from_parts(bank: str, variant: str | None) -> str:
    if variant:
        return f"{bank}/{variant}"
    return bank


def account_label(account: ResolvedAccount) -> str:
    base = account_label_from_parts(account.bank, account.variant)
    return f"{base} ({account.account_number})"


def account_download_path(settings: Settings, account: ResolvedAccount) -> Path:
    return settings.download_path / account.account_type / account.account_number


def resolve_config_path(override: str | Path | None = None) -> Path:
    """Resolve app config path: explicit override, then NETWORTHCSV_CONFIG, then default."""
    if override is not None:
        value = str(override).strip()
        if value:
            return Path(value).expanduser().resolve()

    env_value = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return DEFAULT_CONFIG_PATH.resolve()


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ConfigError(f"config not found: {path}")

    with path.open(encoding="utf-8") as fh:
        loaded = cast(object, json.load(fh))
    if not isinstance(loaded, dict):
        raise ConfigError(f"config must be a JSON object: {path}")
    return cast(dict[str, object], loaded)


def _deep_merge_dict(
    base: dict[str, object],
    overlay: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = _deep_merge_dict(
                cast(dict[str, object], base_value),
                cast(dict[str, object], overlay_value),
            )
        else:
            merged[key] = overlay_value
    return merged


def _is_local_app_config_overlay(path: Path) -> bool:
    return path.name == LOCAL_APP_CONFIG_FILENAME


def _load_app_config_data(resolved: Path) -> dict[str, object]:
    if not _is_local_app_config_overlay(resolved):
        return _load_json_object(resolved)

    base_path = resolved.parent / BASE_APP_CONFIG_FILENAME
    if not base_path.is_file():
        raise ConfigError(f"app config overlay requires base config: {base_path}")

    base_data = _load_json_object(base_path)
    overlay_data = _load_json_object(resolved)
    return _deep_merge_dict(base_data, overlay_data)


def load_app_config(config_path: str | Path) -> AppConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return AppConfig.from_json(
            _load_app_config_data(resolved), config_path=resolved
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise _config_error(resolved, exc) from exc


def load_user_config(config_path: str | Path) -> UserConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return UserConfig.from_json(_load_json_object(resolved), config_path=resolved)
    except (ValidationError, ValueError, TypeError) as exc:
        raise _config_error(resolved, exc) from exc


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_app_config = resolve_config_path(config_path)
    app_config = load_app_config(resolved_app_config)
    user_config = load_user_config(app_config.user_config)
    try:
        return merge_settings(app_config, user_config)
    except (ValidationError, ValueError, TypeError) as exc:
        raise _config_error(
            app_config.user_config,
            exc,
            context=f"app: {resolved_app_config}",
        ) from exc
