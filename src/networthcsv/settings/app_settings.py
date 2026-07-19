"""Runtime AppSettings loaded from accounts.json and environment variables."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, cast

from networthcsv.logging import LogLevel
from networthcsv.settings._load import (
    CONFIG_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    config_error,
    load_accounts_json,
    resolve_config_path,
)
from networthcsv.settings.env_settings import EnvSettings, load_env_settings
from networthcsv.settings.models import (
    AlertSettings,
    EmailSource,
    ResolvedAccount,
    RunSettings,
    ThunderbirdSource,
    UserAccountConfig,
    parse_accounts_config,
    reject_duplicate_accounts,
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

    @classmethod
    def resolve_config_path(cls, override: str | Path | None = None) -> Path:
        return resolve_config_path(override)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> AppSettings:
        resolved_config = resolve_config_path(config_path)
        try:
            accounts = parse_accounts_config(load_accounts_json(resolved_config))
            env_settings = load_env_settings()
            return _build_settings(accounts, env_settings)
        except (ValidationError, ValueError, TypeError) as exc:
            raise config_error(resolved_config, exc) from exc

    @classmethod
    def from_user_accounts(
        cls,
        accounts: Sequence[UserAccountConfig] | Sequence[object],
        *,
        allow_empty: bool = False,
    ) -> AppSettings:
        parsed = _normalize_user_accounts(accounts, allow_empty=allow_empty)
        env_settings = load_env_settings()
        return _build_settings(parsed, env_settings)

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


def _normalize_user_accounts(
    accounts: Sequence[UserAccountConfig] | Sequence[object],
    *,
    allow_empty: bool,
) -> list[UserAccountConfig]:
    if not accounts:
        if allow_empty:
            return []
        raise ValueError("accounts config must contain at least one account")
    if isinstance(accounts[0], UserAccountConfig):
        parsed: list[UserAccountConfig] = list(
            cast(Sequence[UserAccountConfig], accounts)
        )
        reject_duplicate_accounts(parsed)
        return parsed
    return parse_accounts_config(list(accounts), allow_empty=allow_empty)


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


def _build_settings(
    accounts: list[UserAccountConfig],
    env: EnvSettings,
) -> AppSettings:
    from networthcsv.utils.banks import get_handler

    resolved_accounts: list[ResolvedAccount] = []
    for index, user_account in enumerate(accounts):
        bank_key = user_account.bank
        label = account_label_from_parts(bank_key, user_account.variant)
        context = f"accounts[{index}] ({label})"
        try:
            defaults = get_handler(bank_key, user_account.variant).matching_defaults()
            resolved_accounts.append(
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
        source=env.source,
        download_path=env.download_path,
        log_level=env.log_level,
        accounts=resolved_accounts,
        alerts=env.alerts,
        run=RunSettings(),
    )
    settings.validate_run_filter()
    return settings
