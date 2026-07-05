"""Alert system tests."""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from typing import ClassVar, cast
from unittest.mock import MagicMock, patch

from networthcsv.utils.alerts.handlers.console import ConsoleAlertHandler
from networthcsv.utils.alerts.handlers.email import SmtpEmailAlertHandler
from networthcsv.utils.alerts.models import Alert, AlertKind, DeliverMode
from networthcsv.utils.alerts.service import AlertService, build_alert_service
from networthcsv.pipeline.cleanup.statement_text import check_file_marker
from networthcsv.settings import (
    ConsoleAlertSettings,
    EmailAlertSettings,
    EmailAlertsSettings,
)


class _RecordingHandler:
    deliver: ClassVar[DeliverMode] = "immediate"

    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def send(self, alerts: Sequence[Alert]) -> None:
        self.sent.extend(alerts)


class _BatchHandler(_RecordingHandler):
    deliver: ClassVar[DeliverMode] = "batch"


class AlertServiceTests(unittest.TestCase):
    def test_emit_notifies_immediate_handler(self) -> None:
        handler = _RecordingHandler()
        service = AlertService(handler=handler)
        alert = Alert(
            kind=AlertKind.FILE_MARKER_MISSING,
            message="missing",
            account="pnb/platinum",
            source_file="2024-01.pdf",
            file_markers=["1234"],
        )

        service.emit(alert)

        self.assertTrue(service.has_alerts)
        self.assertEqual(service.alerts, (alert,))
        self.assertEqual(handler.sent, [alert])

    def test_flush_notifies_batch_handler(self) -> None:
        handler = _BatchHandler()
        service = AlertService(handler=handler)
        alert = Alert(
            kind=AlertKind.FILE_MARKER_MISSING,
            message="missing",
            account="bob/easy",
            source_file="2024-02.pdf",
            file_markers=["5678"],
        )

        service.emit(alert)
        service.flush()

        self.assertEqual(handler.sent, [alert])

    def test_flush_noop_for_immediate_handler(self) -> None:
        handler = _RecordingHandler()
        service = AlertService(handler=handler)
        alert = Alert(
            kind=AlertKind.FILE_MARKER_MISSING,
            message="missing",
            account="bob/easy",
            source_file="2024-02.pdf",
            file_markers=["5678"],
        )

        service.emit(alert)
        service.flush()

        self.assertEqual(handler.sent, [alert])

    def test_build_alert_service_no_handlers_by_default(self) -> None:
        service = build_alert_service(alerts=None)
        self.assertFalse(service.has_alerts)

    @patch("networthcsv.utils.alerts.service.ConsoleAlertHandler")
    def test_build_alert_service_console(self, mock_console_cls: MagicMock) -> None:
        mock_console_cls.return_value = _RecordingHandler()
        alerts = ConsoleAlertSettings()
        service = build_alert_service(alerts=alerts)
        service.emit(
            Alert(
                kind=AlertKind.FILE_MARKER_MISSING,
                message="missing",
                account="pnb/platinum",
                source_file="2024-01.pdf",
                file_markers=["1234"],
            )
        )
        mock_console_cls.assert_called_once()

    def test_build_alert_service_email_when_configured(self) -> None:
        alerts = EmailAlertsSettings(email=_complete_email_settings())
        with patch(
            "networthcsv.utils.alerts.service.SmtpEmailAlertHandler"
        ) as mock_handler_cls:
            mock_handler_cls.return_value = _BatchHandler()
            service = build_alert_service(alerts=alerts)
            service.emit(
                Alert(
                    kind=AlertKind.FILE_MARKER_MISSING,
                    message="missing",
                    account="pnb/platinum",
                    source_file="2024-01.pdf",
                    file_markers=["1234"],
                )
            )
            service.flush()
        mock_handler_cls.assert_called_once()


class ConsoleAlertHandlerTests(unittest.TestCase):
    @patch("networthcsv.utils.alerts.handlers.console.logger.debug")
    def test_logs_alert(self, mock_debug: MagicMock) -> None:
        handler = ConsoleAlertHandler()
        alert = Alert(
            kind=AlertKind.FILE_MARKER_MISSING,
            message="file marker '1234' not found in 2024-01.pdf",
            account="pnb/platinum",
            source_file="2024-01.pdf",
            file_markers=["1234"],
        )

        handler.send([alert])

        mock_debug.assert_called_once()
        self.assertIn("ALERT", cast(str, mock_debug.call_args.args[0]))


class SmtpEmailAlertHandlerTests(unittest.TestCase):
    @patch("networthcsv.utils.alerts.handlers.email.smtplib.SMTP")
    def test_sends_email(self, mock_smtp_cls: MagicMock) -> None:
        mock_smtp = MagicMock()
        mock_client = MagicMock()
        mock_smtp_cls.return_value = mock_client
        cast(MagicMock, mock_client.__enter__).return_value = mock_smtp
        handler = SmtpEmailAlertHandler(_complete_email_settings())
        alert = Alert(
            kind=AlertKind.FILE_MARKER_MISSING,
            message="file marker '1234' not found in 2024-01.pdf",
            account="pnb/platinum",
            source_file="2024-01.pdf",
            file_markers=["1234"],
        )

        handler.send([alert])

        cast(MagicMock, mock_smtp.starttls).assert_called_once()
        cast(MagicMock, mock_smtp.login).assert_called_once_with(
            "user@example.com", "secret"
        )
        cast(MagicMock, mock_smtp.send_message).assert_called_once()


class CheckFileMarkerAlertIntegrationTests(unittest.TestCase):
    def test_emits_alert_when_service_configured(self) -> None:
        handler = _RecordingHandler()
        service = AlertService(handler=handler)

        result = check_file_marker(
            "no card digits here",
            file_markers=["1234"],
            source_file="2024-01.pdf",
            account_label="pnb/platinum",
            alerts=service,
        )

        self.assertFalse(result)
        self.assertEqual(len(handler.sent), 1)
        self.assertEqual(handler.sent[0].kind, AlertKind.FILE_MARKER_MISSING)


def _complete_email_settings() -> EmailAlertSettings:
    return EmailAlertSettings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="user@example.com",
        password="secret",
        from_address="user@example.com",
        to=["alerts@example.com"],
    )


if __name__ == "__main__":
    _ = unittest.main()
