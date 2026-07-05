"""Email message filtering helpers."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from email.message import EmailMessage, Message
from pathlib import Path

from networthcsv.utils.email.email_message import (
    body_matches,
    from_matches,
    is_pdf_attachment_part,
    message_in_date_range,
    message_matches_account,
    save_attachments,
    subject_matches,
)
from networthcsv.settings import ResolvedAccount


def _account() -> ResolvedAccount:
    return ResolvedAccount.model_validate(
        {
            "bank": "icici",
            "variant": "amazon",
            "account_number": "1234",
            "passwords": ["secret"],
            "mail": {
                "subjects": ["ICICI Bank Credit Card Statement for the period"],
                "body_contains": [],
                "from": ["icicibank.com"],
            },
            "statement": {"text_contains": ["1234"]},
        }
    )


def _statement_msg_with_attachments(
    attachments: list[tuple[str, bytes, str]],
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "ICICI Bank Credit Card Statement for the period"
    msg["From"] = "alerts@icicibank.com"
    msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
    msg.set_content("Statement attached.")
    for filename, payload, maintype_subtype in attachments:
        maintype, subtype = maintype_subtype.split("/", 1)
        msg.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )
    return msg


class SubjectMatchesTests(unittest.TestCase):
    def _msg_with_subject(self, subject: str) -> Message:
        msg = Message()
        msg["Subject"] = subject
        return msg

    def test_single_subject_match(self) -> None:
        msg = self._msg_with_subject("Your PNB Credit Card Statement for the month")
        self.assertTrue(subject_matches(msg, ["PNB Credit Card Statement"]))

    def test_any_subject_matches(self) -> None:
        msg = self._msg_with_subject("ICICI Bank Credit Card Statement for the period")
        subjects = [
            "Amazon Pay ICICI Bank Credit Card Statement for the period",
            "ICICI Bank Credit Card Statement for the period",
        ]
        self.assertTrue(subject_matches(msg, subjects))

    def test_no_match(self) -> None:
        msg = self._msg_with_subject("Random newsletter")
        self.assertFalse(subject_matches(msg, ["PNB Credit Card Statement"]))

    def test_case_insensitive(self) -> None:
        msg = self._msg_with_subject("first wow! credit card statement")
        self.assertTrue(subject_matches(msg, ["FIRST WOW! Credit Card Statement"]))


class BodyMatchesTests(unittest.TestCase):
    def _msg_with_body(
        self, body: str, *, content_type: str = "text/plain"
    ) -> EmailMessage:
        msg = EmailMessage()
        msg.set_content(body, subtype=content_type.split("/")[1])
        return msg

    def test_plain_text_match(self) -> None:
        msg = self._msg_with_body("Your BOB EASY credit card statement is attached.")
        self.assertTrue(body_matches(msg, ["BOB EASY credit card"]))

    def test_no_match(self) -> None:
        msg = self._msg_with_body("Unrelated newsletter content.")
        self.assertFalse(body_matches(msg, ["BOB EASY credit card"]))

    def test_case_insensitive(self) -> None:
        msg = self._msg_with_body("amazon pay icici bank credit card statement")
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_empty_body_contains_passes(self) -> None:
        msg = self._msg_with_body("anything")
        self.assertTrue(body_matches(msg, []))

    def test_multipart_searches_all_text_parts(self) -> None:
        msg = EmailMessage()
        msg.set_content("Amazon Pay ICICI Bank Credit Card statement attached.")
        msg.add_alternative(
            "<html><body><p>HTML version</p></body></html>",
            subtype="html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_html_included_when_plain_lacks_match(self) -> None:
        msg = EmailMessage()
        msg.set_content("Plain part without the marker.")
        msg.add_alternative(
            "<html><body>Unique HTML marker text</body></html>",
            subtype="html",
        )
        self.assertTrue(body_matches(msg, ["Unique HTML marker text"]))

    def test_html_only_message(self) -> None:
        msg = EmailMessage()
        msg.add_alternative(
            "<html><body>Amazon Pay ICICI Bank Credit Card</body></html>",
            subtype="html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_html_only_raw_match(self) -> None:
        msg = self._msg_with_body(
            "<html><body><p>Amazon Pay ICICI Bank Credit Card</p></body></html>",
            content_type="text/html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_all_body_contains_must_match(self) -> None:
        msg = self._msg_with_body("alpha beta gamma")
        self.assertTrue(body_matches(msg, ["alpha", "gamma"]))
        self.assertFalse(body_matches(msg, ["alpha", "missing"]))

    def test_html_tag_substring_match(self) -> None:
        msg = self._msg_with_body(
            "<html><head><title>Signet</title></head><body></body></html>",
            content_type="text/html",
        )
        self.assertTrue(body_matches(msg, ["<title>Signet</title>"]))


class FromMatchesTests(unittest.TestCase):
    def _msg_with_from(self, from_header: str) -> Message:
        msg = Message()
        msg["From"] = from_header
        return msg

    def test_full_email_match(self) -> None:
        msg = self._msg_with_from("alerts@icicibank.com")
        self.assertTrue(from_matches(msg, ["alerts@icicibank.com"]))

    def test_domain_match(self) -> None:
        msg = self._msg_with_from("statements@icicibank.com")
        self.assertTrue(from_matches(msg, ["icicibank.com"]))

    def test_domain_does_not_substring_match(self) -> None:
        msg = self._msg_with_from("user@evil-icicibank.com")
        self.assertFalse(from_matches(msg, ["icicibank.com"]))

    def test_display_name_wrapper(self) -> None:
        msg = self._msg_with_from('"ICICI Bank" <alerts@icicibank.com>')
        self.assertTrue(from_matches(msg, ["alerts@icicibank.com"]))

    def test_case_insensitive(self) -> None:
        msg = self._msg_with_from("Alerts@ICICIBank.com")
        self.assertTrue(from_matches(msg, ["alerts@icicibank.com"]))

    def test_no_match(self) -> None:
        msg = self._msg_with_from("spam@example.com")
        self.assertFalse(from_matches(msg, ["icicibank.com"]))

    def test_empty_from_filters_passes(self) -> None:
        msg = self._msg_with_from("spam@example.com")
        self.assertTrue(from_matches(msg, []))

    def test_multiple_from_addresses(self) -> None:
        msg = self._msg_with_from("Alice <alice@example.com>, Bob <bob@bank.com>")
        self.assertTrue(from_matches(msg, ["bank.com"]))
        self.assertTrue(from_matches(msg, ["bob@bank.com"]))
        self.assertFalse(from_matches(msg, ["other.com"]))


class MessageDateRangeTests(unittest.TestCase):
    def _msg_on(self, year: int, month: int) -> EmailMessage:
        month_names = (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        )
        msg = _statement_msg_with_attachments(
            [("statement.pdf", b"%PDF-1.4", "application/pdf")]
        )
        msg.replace_header(
            "Date",
            f"Mon, 15 {month_names[month - 1]} {year} 10:00:00 +0000",
        )
        return msg

    def test_message_in_date_range_inclusive_bounds(self) -> None:
        msg = self._msg_on(2024, 3)
        self.assertTrue(message_in_date_range(msg, date(2024, 1, 1), date(2024, 3, 1)))
        self.assertFalse(message_in_date_range(msg, date(2024, 4, 1), date(2024, 6, 1)))
        self.assertFalse(
            message_in_date_range(msg, date(2023, 1, 1), date(2023, 12, 1))
        )

    def test_message_matches_account_respects_closing_date(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                **_account().model_dump(),
                "opening_date": date(2024, 1, 1),
                "closing_date": date(2024, 2, 1),
            }
        )
        inside = self._msg_on(2024, 3)
        outside = self._msg_on(2024, 4)
        self.assertTrue(
            message_matches_account(
                inside,
                account,
                date(2024, 1, 1),
                date(2024, 3, 1),
            )
        )
        self.assertFalse(
            message_matches_account(
                outside,
                account,
                date(2024, 1, 1),
                date(2024, 3, 1),
            )
        )


class PdfAttachmentFilterTests(unittest.TestCase):
    def test_message_matches_when_pdf_attached(self) -> None:
        msg = _statement_msg_with_attachments(
            [("statement.pdf", b"%PDF-1.4", "application/pdf")]
        )
        self.assertTrue(message_matches_account(msg, _account(), None))

    def test_message_rejects_csv_only_attachment(self) -> None:
        msg = _statement_msg_with_attachments(
            [("transactions.csv", b"a,b,c", "text/csv")]
        )
        self.assertFalse(message_matches_account(msg, _account(), None))

    def test_uppercase_pdf_extension_matches(self) -> None:
        msg = _statement_msg_with_attachments(
            [("statement.PDF", b"%PDF-1.4", "application/pdf")]
        )
        self.assertTrue(message_matches_account(msg, _account(), None))

    def test_application_pdf_without_filename_matches(self) -> None:
        msg = EmailMessage()
        msg["Subject"] = "ICICI Bank Credit Card Statement for the period"
        msg["From"] = "alerts@icicibank.com"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
        msg.set_content("Statement attached.")
        msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf")
        self.assertTrue(message_matches_account(msg, _account(), None))
        parts = list(msg.walk())
        pdf_parts = [part for part in parts if is_pdf_attachment_part(part)]
        self.assertEqual(len(pdf_parts), 1)

    def test_save_attachments_writes_pdf_only(self) -> None:
        msg = _statement_msg_with_attachments(
            [
                ("statement.pdf", b"%PDF-1.4", "application/pdf"),
                ("transactions.csv", b"a,b,c", "text/csv"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            saved = save_attachments(msg, download_dir, "INBOX")
            self.assertEqual(saved, 1)
            files = list(download_dir.glob("*.pdf"))
            self.assertEqual(len(files), 1)
            self.assertFalse(list(download_dir.glob("*.csv")))


if __name__ == "__main__":
    _ = unittest.main()
