"""Operational settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from networthcsv.logging import LogLevel
from networthcsv.settings._load import _ensure_dotenv_loaded, project_root, resolve_path
from networthcsv.settings.models import (
    AlertSettings,
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
    EmailSource,
    EmailSourceSettings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)


@dataclass(frozen=True)
class EnvSettings:
    source: ThunderbirdSource | EmailSource
    download_path: Path
    log_level: LogLevel
    alerts: AlertSettings | None


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false), got {raw!r}")


def _env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def _load_source(base: Path) -> ThunderbirdSource | EmailSource:
    source_type = _required_env("SOURCE_TYPE").lower()
    if source_type == "thunderbird":
        profile_raw = _required_env("THUNDERBIRD_PROFILE")
        return ThunderbirdSource(
            thunderbird=ThunderbirdSourceSettings(
                profile=resolve_path(profile_raw, base),
            )
        )
    if source_type == "email":
        return EmailSource(
            email=EmailSourceSettings(
                host=_required_env("IMAP_HOST"),
                port=_env_int("IMAP_PORT", default=993),
                username=_required_env("IMAP_USERNAME"),
                password=_required_env("IMAP_PASSWORD"),
                folder=os.environ.get("IMAP_FOLDER", "INBOX").strip() or "INBOX",
                use_ssl=_env_bool("IMAP_USE_SSL", default=True),
            )
        )
    raise ValueError("SOURCE_TYPE must be 'thunderbird' or 'email'")


def _load_alerts() -> AlertSettings | None:
    alerts_type = (
        (os.environ.get("ALERTS_TYPE", "console") or "console").strip().lower()
    )
    if alerts_type == "console":
        return ConsoleAlertSettings()
    if alerts_type == "email":
        return EmailAlertsSettings(
            email=EmailAlertSettings(
                smtp_host=_required_env("SMTP_HOST"),
                smtp_port=_env_int("SMTP_PORT", default=587),
                use_tls=_env_bool("SMTP_USE_TLS", default=True),
                username=_required_env("SMTP_USERNAME"),
                password=_required_env("SMTP_PASSWORD"),
                from_address=_required_env("SMTP_FROM_ADDRESS"),
                to=_required_env("SMTP_TO").split(","),
            )
        )
    raise ValueError("ALERTS_TYPE must be 'console' or 'email'")


def load_env_settings() -> EnvSettings:
    _ensure_dotenv_loaded()
    base = project_root()
    log_level_raw = (os.environ.get("LOG_LEVEL", "info") or "info").strip().lower()
    if log_level_raw not in {"debug", "info"}:
        raise ValueError("LOG_LEVEL must be 'debug' or 'info'")
    log_level = cast(LogLevel, log_level_raw)
    download_raw = _required_env("DOWNLOAD_PATH")
    return EnvSettings(
        source=_load_source(base),
        download_path=resolve_path(download_raw, base),
        log_level=log_level,
        alerts=_load_alerts(),
    )
