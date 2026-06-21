"""Console alert handler."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import ClassVar

from src.utils.alerts.models import Alert, DeliverMode

logger = logging.getLogger(__name__)


class ConsoleAlertHandler:
    deliver: ClassVar[DeliverMode] = "immediate"

    def send(self, alerts: Sequence[Alert]) -> None:
        for alert in alerts:
            logger.debug(
                "ALERT [%s] %s (account=%s, file=%s, identifier=%r)",
                alert.kind,
                alert.message,
                alert.account,
                alert.source_file,
                alert.identifier,
            )
