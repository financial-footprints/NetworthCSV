"""Thunderbird extraction helpers."""

from __future__ import annotations

import unittest
from email.message import Message

from src.pipeline.thunderbird import subject_matches


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


if __name__ == "__main__":
    unittest.main()
