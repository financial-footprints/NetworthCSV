"""Load settings from app.config.json and user.config.json."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, ClassVar, Literal, cast

from src.logging_config import LogLevel

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "app.config.json"
BASE_APP_CONFIG_FILENAME = "app.config.json"
LOCAL_APP_CONFIG_FILENAME = "app.config.local.json"
CONFIG_ENV_VAR = "NETWORTHCSV_CONFIG"

_MATCHING_FIELD_NAMES = frozenset(
    {"subjects", "bodies", "from_filters", "start_marker", "end_marker", "information_markers"}
)


def normalize_bank(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("bank is required")
    if "/" in raw or "\\" in raw:
        raise ValueError("bank must not contain path separators")
    return raw


def normalize_variant(value: object) -> str | None:
    if value is None or value == "":
        return None
    variant = str(value).strip().lower()
    if not variant:
        return None
    if "/" in variant or "\\" in variant:
        raise ValueError("variant must not contain path separators")
    return variant


def normalize_subjects(value: object) -> list[str]:
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


def normalize_marker(value: object) -> str | None:
    if value is None or value == "":
        return None
    marker = str(value).strip()
    return marker or None


def normalize_information_markers(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        raise ValueError("information_markers must be a string or an array")
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        marker = str(item).strip()
        if marker and marker not in seen:
            seen.add(marker)
            unique.append(marker)
    return unique


def normalize_bodies(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        raise ValueError("bodies must be a string or an array")
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        body = str(item).strip()
        if body and body.lower() not in seen:
            seen.add(body.lower())
            unique.append(body)
    return unique


def normalize_from(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        raise ValueError("from must be a string or an array")
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        entry = str(item).strip().lower()
        if not entry:
            continue
        if any(ch.isspace() for ch in entry):
            raise ValueError("from entries must not contain whitespace")
        if "@" in entry:
            local, sep, domain = entry.partition("@")
            if not local or not sep or not domain or "@" in domain:
                raise ValueError(f"invalid from email address: {entry!r}")
        if entry not in seen:
            seen.add(entry)
            unique.append(entry)
    return unique


def normalize_identifier(value: object) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise ValueError("identifier is required")
    return identifier


def normalize_passwords(value: object) -> list[str]:
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
OptionalSubjects = Annotated[list[str] | None, BeforeValidator(_optional(normalize_subjects))]
Bodies = Annotated[list[str], BeforeValidator(normalize_bodies)]
OptionalBodies = Annotated[list[str] | None, BeforeValidator(_optional(normalize_bodies))]
FromFilters = Annotated[list[str], BeforeValidator(normalize_from)]
OptionalFromFilters = Annotated[list[str] | None, BeforeValidator(_optional(normalize_from))]
Marker = Annotated[str | None, BeforeValidator(normalize_marker)]
InformationMarkers = Annotated[list[str], BeforeValidator(normalize_information_markers)]
OptionalInformationMarkers = Annotated[
    list[str] | None, BeforeValidator(_optional(normalize_information_markers))
]
BankName = Annotated[str, BeforeValidator(normalize_bank)]
OptionalBankName = Annotated[str | None, BeforeValidator(_optional_bank)]
VariantName = Annotated[str | None, BeforeValidator(normalize_variant)]
Identifier = Annotated[str, BeforeValidator(normalize_identifier)]
Passwords = Annotated[list[str], BeforeValidator(normalize_passwords)]


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


class MatchingFields(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)

    subjects: Subjects
    bodies: Bodies = []
    from_filters: FromFilters = Field(default_factory=list, alias="from")
    start_marker: Marker = None
    end_marker: Marker = None
    information_markers: InformationMarkers = []


class VariantOverride(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)

    subjects: OptionalSubjects = None
    bodies: OptionalBodies = None
    from_filters: OptionalFromFilters = Field(default=None, alias="from")
    start_marker: Marker = None
    end_marker: Marker = None
    information_markers: OptionalInformationMarkers = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> VariantOverride:
        if (
            self.subjects is None
            and self.bodies is None
            and self.from_filters is None
            and self.start_marker is None
            and self.end_marker is None
            and self.information_markers is None
        ):
            raise ValueError("variant override must set at least one field")
        return self


BankVariantEntry = MatchingFields | VariantOverride


class AppConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    user_config: Path
    banks: dict[str, dict[str, BankVariantEntry]] = Field(min_length=1)

    @field_validator("user_config", mode="before")
    @classmethod
    def validate_user_config(cls, value: object) -> object:
        if value is None or str(value).strip() == "":
            raise ValueError("user_config is required")
        return value

    @field_validator("banks", mode="before")
    @classmethod
    def normalize_banks(cls, value: object) -> dict[str, dict[str, BankVariantEntry]]:
        if not isinstance(value, dict):
            raise ValueError("banks must be an object")
        banks_raw = cast(dict[str, object], value)
        normalized: dict[str, dict[str, BankVariantEntry]] = {}
        for bank_key, bank_value in banks_raw.items():
            if not isinstance(bank_value, dict):
                raise ValueError(f"bank {bank_key!r} must be an object of variants")
            variants_raw = cast(dict[str, object], bank_value)
            variants: dict[str, BankVariantEntry] = {}
            for variant_key, variant_value in variants_raw.items():
                variant_name = normalize_variant(variant_key)
                if variant_name is None:
                    raise ValueError("variant keys must be non-empty")
                if variant_name == "default":
                    variants[variant_name] = MatchingFields.model_validate(variant_value)
                else:
                    variants[variant_name] = VariantOverride.model_validate(variant_value)
            if not variants:
                raise ValueError(f"bank {bank_key!r} must contain at least one variant")
            if "default" not in variants:
                raise ValueError(f"bank {normalize_bank(bank_key)!r} must define a default variant")
            normalized[normalize_bank(bank_key)] = variants
        if not normalized:
            raise ValueError("banks must contain at least one entry")
        return normalized

    @classmethod
    def from_json(cls, data: dict[str, object], *, config_path: Path) -> AppConfig:
        base = config_path.parent
        user_config_raw = data.get("user_config")
        if not user_config_raw:
            raise ValueError("user_config is required")
        return cls.model_validate(
            {
                "user_config": _resolve_path(user_config_raw, base),
                "banks": data.get("banks", {}),
            }
        )


class UserAccountConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)

    bank: BankName
    variant: VariantName = None
    identifier: Identifier
    passwords: Passwords
    subjects: OptionalSubjects = None
    bodies: OptionalBodies = None
    from_filters: OptionalFromFilters = Field(default=None, alias="from")
    start_marker: Marker = None
    end_marker: Marker = None
    information_markers: OptionalInformationMarkers = None


def normalize_alert_recipients(value: object) -> list[str]:
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = cast(list[object], value)
    else:
        raise ValueError("to must be a string or a non-empty array")
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        address = str(item).strip()
        if not address:
            continue
        lowered = address.lower()
        if lowered not in seen:
            seen.add(lowered)
            unique.append(address)
    if not unique:
        raise ValueError("to must contain at least one non-empty email address")
    return unique


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

    bank: OptionalBankName = None
    variant: VariantName = None
    fy: Marker = None
    force_text_extract: bool = False
    create_combined_csv: bool = False


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


class UserConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    source: SourceSettings
    download_path: Path
    log_level: LogLevel = "info"
    start_date: date | None = None
    accounts: list[UserAccountConfig] = Field(min_length=1)
    alerts: AlertSettings | None = None
    run: RunSettings | None = None

    @model_validator(mode="after")
    def validate_run_filter(self) -> UserConfig:
        if self.run is None:
            return self
        if self.run.variant is not None and self.run.bank is None:
            raise ValueError("run.variant requires run.bank")
        if self.run.bank is not None:
            matches = [
                account
                for account in self.accounts
                if account.bank == self.run.bank
                and (self.run.variant is None or account.variant == self.run.variant)
            ]
            if not matches:
                known = ", ".join(
                    account_label_from_parts(account.bank, account.variant)
                    for account in self.accounts
                )
                raise ValueError(f"run filter matches no account (known: {known})")
        return self

    @model_validator(mode="after")
    def reject_duplicate_accounts(self) -> UserConfig:
        seen: set[tuple[str, str]] = set()
        for account in self.accounts:
            key = (account.bank, account.variant or "")
            if key in seen:
                label = account_label_from_parts(account.bank, account.variant)
                raise ValueError(f"duplicate account: {label}")
            seen.add(key)
        return self

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
    def from_json(cls, data: dict[str, object], *, config_path: Path) -> UserConfig:
        base = config_path.parent
        download_raw = data.get("download_path")
        if not download_raw:
            raise ValueError("download_path is required")

        if "mbox" in data:
            raise ValueError(
                "mbox is no longer supported; remove mbox from user config (Thunderbird source always scans all profile folders)"
            )

        source_raw = data.get("source")
        if source_raw is not None:
            source = _parse_source_settings(source_raw, base)
        elif "profile" in data:
            profile_raw = data.get("profile")
            if not profile_raw:
                raise ValueError("profile must be a non-empty path when using legacy config")
            source = ThunderbirdSource(
                thunderbird=ThunderbirdSourceSettings(
                    profile=_resolve_path(profile_raw, base),
                )
            )
        else:
            raise ValueError("source is required (or legacy top-level profile for thunderbird)")

        return cls.model_validate(
            {
                "source": source,
                "download_path": _resolve_path(download_raw, base),
                "log_level": data.get("log_level", "info"),
                "start_date": data.get("start_date"),
                "accounts": data.get("accounts", []),
                "alerts": data.get("alerts"),
                "run": data.get("run"),
            }
        )


class ResolvedAccount(MatchingFields):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", populate_by_name=True, frozen=True
    )

    bank: str
    variant: str | None = None
    identifier: str
    passwords: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class Settings:
    source: ThunderbirdSource | EmailSource
    download_path: Path
    accounts: list[ResolvedAccount]
    alerts: ConsoleAlertSettings | EmailAlertsSettings | None
    run: RunSettings
    log_level: LogLevel = "info"
    start_date: date | None = None


def _parse_source_settings(raw: object, base: Path) -> ThunderbirdSource | EmailSource:
    if not isinstance(raw, dict):
        raise ValueError("source must be an object")
    source_data = cast(dict[str, object], raw)
    source_type = source_data.get("type")
    if source_type == "thunderbird":
        thunderbird_raw = source_data.get("thunderbird")
        if not isinstance(thunderbird_raw, dict):
            raise ValueError("source.thunderbird is required when type is thunderbird")
        thunderbird_data = cast(dict[str, object], thunderbird_raw)
        profile_raw = thunderbird_data.get("profile")
        if not profile_raw:
            raise ValueError("source.thunderbird.profile is required")
        return ThunderbirdSource(
            thunderbird=ThunderbirdSourceSettings(
                profile=_resolve_path(profile_raw, base),
            )
        )
    if source_type == "email":
        email_raw = source_data.get("email")
        if not isinstance(email_raw, dict):
            raise ValueError("source.email is required when type is email")
        return EmailSource(email=EmailSourceSettings.model_validate(email_raw))
    raise ValueError("source.type must be 'thunderbird' or 'email'")


def _matching_overlay(model: BaseModel) -> dict[str, object]:
    dumped = cast(dict[str, object], model.model_dump(exclude_none=True))
    return {key: value for key, value in dumped.items() if key in _MATCHING_FIELD_NAMES}


def merge_matching(base: MatchingFields, *overlays: BaseModel) -> MatchingFields:
    merged = base.model_dump()
    for overlay in overlays:
        merged.update(_matching_overlay(overlay))
    return MatchingFields.model_validate(merged)


def _resolve_variant_defaults(
    bank_variants: dict[str, BankVariantEntry], variant: str | None
) -> MatchingFields:
    default_entry = bank_variants["default"]
    if not isinstance(default_entry, MatchingFields):
        raise ValueError("bank must define a default variant with subjects")
    if variant is None or variant == "default":
        return default_entry
    overlay = bank_variants.get(variant)
    if overlay is None:
        return default_entry
    if isinstance(overlay, MatchingFields):
        return overlay
    return merge_matching(default_entry, overlay)


def _resolved_account(
    user_account: UserAccountConfig, defaults: MatchingFields, *, bank_key: str
) -> ResolvedAccount:
    matching = merge_matching(defaults, user_account)
    return ResolvedAccount.model_validate(
        {
            "bank": bank_key,
            "variant": user_account.variant,
            "identifier": user_account.identifier,
            "passwords": user_account.passwords,
            **matching.model_dump(),
        }
    )


def merge_settings(app: AppConfig, user: UserConfig) -> Settings:
    accounts: list[ResolvedAccount] = []
    for user_account in user.accounts:
        bank_key = user_account.bank
        bank_variants = app.banks.get(bank_key)
        if bank_variants is None:
            known = ", ".join(sorted(app.banks))
            raise ValueError(
                f"bank {bank_key!r} is not defined in app config banks (known: {known})"
            )
        defaults = _resolve_variant_defaults(bank_variants, user_account.variant)
        accounts.append(_resolved_account(user_account, defaults, bank_key=bank_key))

    return Settings(
        source=user.source,
        download_path=user.download_path,
        log_level=user.log_level,
        start_date=user.start_date,
        accounts=accounts,
        alerts=user.alerts,
        run=user.run or RunSettings(),
    )


def accounts_to_run(settings: Settings) -> list[ResolvedAccount]:
    run = settings.run
    if run.bank is None:
        return list(settings.accounts)
    matches = [
        account
        for account in settings.accounts
        if account.bank == run.bank
        and (run.variant is None or account.variant == run.variant)
    ]
    if not matches:
        known = ", ".join(account_label(account) for account in settings.accounts)
        raise SystemExit(f"error: run filter matches no account (known: {known})")
    return matches


def account_label_from_parts(bank: str, variant: str | None) -> str:
    if variant:
        return f"{bank}/{variant}"
    return bank


def account_label(account: ResolvedAccount) -> str:
    return account_label_from_parts(account.bank, account.variant)


def account_download_path(settings: Settings, account: ResolvedAccount) -> Path:
    base = settings.download_path / account.bank
    if account.variant:
        return base / account.variant
    return base


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
        raise SystemExit(f"error: config not found: {path}")

    with path.open(encoding="utf-8") as fh:
        loaded = cast(object, json.load(fh))
    if not isinstance(loaded, dict):
        raise SystemExit(f"error: config must be a JSON object: {path}")
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
        raise SystemExit(
            f"error: app config overlay requires base config: {base_path}"
        )

    base_data = _load_json_object(base_path)
    overlay_data = _load_json_object(resolved)
    return _deep_merge_dict(base_data, overlay_data)


def load_app_config(config_path: str | Path) -> AppConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return AppConfig.from_json(_load_app_config_data(resolved), config_path=resolved)
    except (ValidationError, ValueError, TypeError) as exc:
        raise SystemExit(f"error: invalid app config {resolved}: {exc}") from exc


def load_user_config(config_path: str | Path) -> UserConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return UserConfig.from_json(_load_json_object(resolved), config_path=resolved)
    except (ValidationError, ValueError, TypeError) as exc:
        raise SystemExit(f"error: invalid user config {resolved}: {exc}") from exc


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_app_config = resolve_config_path(config_path)
    app_config = load_app_config(resolved_app_config)
    user_config = load_user_config(app_config.user_config)
    try:
        return merge_settings(app_config, user_config)
    except (ValidationError, ValueError, TypeError) as exc:
        raise SystemExit(
            f"error: invalid merged config (app: {resolved_app_config}, user: {app_config.user_config}): {exc}"
        ) from exc
