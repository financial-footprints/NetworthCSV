"""Runtime context passed through pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass

from src.alerts.service import AlertService
from src.settings import Settings


@dataclass(frozen=True)
class RunContext:
    settings: Settings
    alerts: AlertService
