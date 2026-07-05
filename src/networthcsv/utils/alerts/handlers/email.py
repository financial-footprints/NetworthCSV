"""SMTP email alert handler."""

from __future__ import annotations

import logging
import smtplib
from collections.abc import Sequence
from typing import ClassVar
from email.message import EmailMessage

from networthcsv.utils.alerts.models import Alert, DeliverMode
from networthcsv.settings import EmailAlertSettings

logger = logging.getLogger(__name__)


class SmtpEmailAlertHandler:
    deliver: ClassVar[DeliverMode] = "batch"
    _config: EmailAlertSettings

    def __init__(self, config: EmailAlertSettings) -> None:
        self._config = config

    def send(self, alerts: Sequence[Alert]) -> None:
        if not alerts:
            return

        body_lines = [
            f"NetworthCSV raised {len(alerts)} alert(s):",
            "",
        ]
        for index, alert in enumerate(alerts, start=1):
            body_lines.extend(
                [
                    f"{index}. [{alert.kind}] {alert.message}",
                    f"   account: {alert.account}",
                    f"   file: {alert.source_file}",
                    f"   file_markers: {alert.file_markers!r}",
                    "",
                ]
            )

        message = EmailMessage()
        message["Subject"] = f"NetworthCSV alert: {len(alerts)} issue(s)"
        message["From"] = self._config.from_address
        message["To"] = ", ".join(self._config.to)
        message.set_content("\n".join(body_lines).rstrip())

        try:
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as smtp:
                if self._config.use_tls:
                    _ = smtp.starttls()
                _ = smtp.login(self._config.username, self._config.password)
                _ = smtp.send_message(message)
        except smtplib.SMTPException as exc:
            logger.warning("failed to send alert email: %s", exc)
        except OSError as exc:
            logger.warning("failed to connect to SMTP server: %s", exc)
