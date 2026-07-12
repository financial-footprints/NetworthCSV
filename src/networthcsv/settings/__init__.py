"""Load and merge configuration from app.config.json and user.config.json.

Public surface: AppSettings (runtime), ResolvedAccount, RunSettings, and the
source/alert models other packages need. Validators and JSON loaders are private.
"""

from __future__ import annotations

from networthcsv.settings.app_settings import AppSettings
from networthcsv.settings.models import (
    AlertSettings,
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
    EmailSource,
    EmailSourceSettings,
    ResolvedAccount,
    RunSettings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)

__all__ = [
    "AlertSettings",
    "AppSettings",
    "ConsoleAlertSettings",
    "EmailAlertSettings",
    "EmailAlertsSettings",
    "EmailSource",
    "EmailSourceSettings",
    "ResolvedAccount",
    "RunSettings",
    "ThunderbirdSource",
    "ThunderbirdSourceSettings",
]
