"""Thunderbird extraction helpers."""

from __future__ import annotations

import unittest
from email.message import EmailMessage, Message

from src.pipeline.thunderbird import (
    body_matches,
    from_matches,
    subject_matches,
)


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
    def _msg_with_body(self, body: str, *, content_type: str = "text/plain") -> EmailMessage:
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

    def test_empty_bodies_passes(self) -> None:
        msg = self._msg_with_body("anything")
        self.assertTrue(body_matches(msg, []))

    def test_multipart_prefers_plain(self) -> None:
        msg = EmailMessage()
        msg.set_content("Amazon Pay ICICI Bank Credit Card statement attached.")
        msg.add_alternative(
            "<html><body><p>HTML version</p></body></html>",
            subtype="html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_html_fallback_when_no_plain(self) -> None:
        msg = EmailMessage()
        msg.add_alternative(
            "<html><body>Amazon Pay ICICI Bank Credit Card</body></html>",
            subtype="html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))

    def test_html_only_strips_tags(self) -> None:
        msg = self._msg_with_body(
            "<html><body><p>Amazon Pay ICICI Bank Credit Card</p></body></html>",
            content_type="text/html",
        )
        self.assertTrue(body_matches(msg, ["Amazon Pay ICICI Bank Credit Card"]))


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


if __name__ == "__main__":
    _ = unittest.main()
