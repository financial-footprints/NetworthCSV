"""Runtime context passed through pipeline stages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from networthcsv.utils.alerts.service import AlertService
from networthcsv.pipeline.reporter import NullRunReporter, RunReporter
from networthcsv.settings import AppSettings


CancelChecker = Callable[[], bool]


@dataclass(frozen=True)
class RunContext:
    settings: AppSettings
    alerts: AlertService
    reporter: RunReporter = field(default_factory=NullRunReporter)
    should_cancel: CancelChecker | None = None
