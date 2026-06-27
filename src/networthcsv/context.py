"""Runtime context passed through pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field

from networthcsv.utils.alerts.service import AlertService
from networthcsv.pipeline.reporter import NullRunReporter, RunReporter
from networthcsv.settings import Settings


@dataclass(frozen=True)
class RunContext:
    settings: Settings
    alerts: AlertService
    reporter: RunReporter = field(default_factory=NullRunReporter)
