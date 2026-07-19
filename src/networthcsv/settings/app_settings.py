"""Runtime AppSettings loaded from app.config.json and user.config.json."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import ClassVar

from networthcsv.logging import LogLevel
from networthcsv.settings._load import (
    CONFIG_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    config_error,
    load_app_config_data,
    load_json_object,
    resolve_config_path,
)
from networthcsv.settings.models import (
    AlertSettings,
    AppConfig,
    EmailSource,
    ResolvedAccount,
    RunSettings,
    ThunderbirdSource,
    UserAccountConfig,
    UserConfig,
)
from networthcsv.utils.account import account_label_from_parts
from networthcsv.utils.banks.account_matching import AccountMatching, MatchingFields
from pydantic import ValidationError


@dataclass(frozen=True)
class AppSettings:
    """Merged runtime settings consumed by the pipeline."""

    CONFIG_ENV_VAR: ClassVar[str] = CONFIG_ENV_VAR
    DEFAULT_CONFIG_PATH: ClassVar[Path] = DEFAULT_CONFIG_PATH

    source: ThunderbirdSource | EmailSource
    download_path: Path
    accounts: list[ResolvedAccount]
    alerts: AlertSettings | None
    run: RunSettings
    log_level: LogLevel = "info"
    start_date: date | None = None

    @classmethod
    def resolve_config_path(cls, override: str | Path | None = None) -> Path:
        return resolve_config_path(override)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> AppSettings:
        resolved_app_config = resolve_config_path(config_path)
        app_config = _load_app_config(resolved_app_config)
        user_config = _load_user_config(app_config.user_config)
        try:
            return _merge_settings(app_config, user_config)
        except (ValidationError, ValueError, TypeError) as exc:
            raise config_error(
                app_config.user_config,
                exc,
                context=f"app: {resolved_app_config}",
            ) from exc

    def accounts_to_run(self) -> list[ResolvedAccount]:
        if self.run.identifier is None:
            return list(self.accounts)
        return [
            account
            for account in self.accounts
            if _account_matches_run_filter(account, self.run)
        ]

    def validate_run_filter(self) -> None:
        """Validate run filter against resolved accounts (e.g. after CLI overrides)."""
        _validate_run_filter(self.run, self.accounts)

    def with_run(self, run: RunSettings) -> AppSettings:
        updated = replace(self, run=run)
        updated.validate_run_filter()
        return updated


def _known_bank_names() -> str:
    from networthcsv.utils.banks import list_handlers

    banks = sorted({key.split("/")[0] for key in list_handlers()})
    return ", ".join(banks)


def _resolved_account(
    user_account: UserAccountConfig, defaults: MatchingFields, *, bank_key: str
) -> ResolvedAccount:
    matching = AccountMatching.merge(defaults, user_account)
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


def _merge_settings(app: AppConfig, user: UserConfig) -> AppSettings:
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

    settings = AppSettings(
        source=user.source,
        download_path=user.download_path,
        log_level=user.log_level,
        start_date=user.start_date,
        accounts=accounts,
        alerts=user.alerts,
        run=user.run or RunSettings(),
    )
    settings.validate_run_filter()
    return settings


def _load_app_config(config_path: str | Path) -> AppConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return AppConfig.from_json(load_app_config_data(resolved), config_path=resolved)
    except (ValidationError, ValueError, TypeError) as exc:
        raise config_error(resolved, exc) from exc


def _load_user_config(config_path: str | Path) -> UserConfig:
    resolved = Path(config_path).expanduser().resolve()
    try:
        return UserConfig.from_json(load_json_object(resolved), config_path=resolved)
    except (ValidationError, ValueError, TypeError) as exc:
        raise config_error(resolved, exc) from exc
