"""Alert collection and dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Protocol

from networthcsv.utils.alerts.handlers.console import ConsoleAlertHandler
from networthcsv.utils.alerts.handlers.email import SmtpEmailAlertHandler
from networthcsv.utils.alerts.models import Alert, DeliverMode
from networthcsv.settings import (
    AlertSettings,
    ConsoleAlertSettings,
    EmailAlertsSettings,
)


class AlertHandler(Protocol):
    deliver: ClassVar[DeliverMode]

    def send(self, alerts: Sequence[Alert]) -> None: ...


class AlertService:
    def __init__(self, *, handler: AlertHandler | None) -> None:
        self._handler: AlertHandler | None = handler
        self._alerts: list[Alert] = []

    @property
    def has_alerts(self) -> bool:
        return bool(self._alerts)

    @property
    def alerts(self) -> tuple[Alert, ...]:
        return tuple(self._alerts)

    def emit(self, alert: Alert) -> None:
        self._alerts.append(alert)
        if self._handler is not None and self._handler.deliver == "immediate":
            self._handler.send([alert])

    def flush(self) -> None:
        if (
            not self._alerts
            or self._handler is None
            or self._handler.deliver != "batch"
        ):
            return
        self._handler.send(self._alerts)


def build_alert_service(*, alerts: AlertSettings | None) -> AlertService:
    if alerts is None:
        return AlertService(handler=None)

    if isinstance(alerts, ConsoleAlertSettings):
        handler = ConsoleAlertHandler()
        return AlertService(handler=handler)

    assert isinstance(alerts, EmailAlertsSettings)
    return AlertService(handler=SmtpEmailAlertHandler(alerts.email))
