"""IMAP extract helpers."""

from __future__ import annotations

import unittest
from datetime import date

from src.pipeline.get_statements.imap import build_gmail_raw_query, build_imap_search_criteria


class BuildImapSearchTests(unittest.TestCase):
    def test_gmail_raw_query_with_subjects_and_date(self) -> None:
        query = build_gmail_raw_query(
            ["ICICI Bank Credit Card Statement for the period"],
            date(2020, 1, 15),
        )
        self.assertIn("has:attachment", query)
        self.assertIn('subject:"ICICI Bank Credit Card Statement for the period"', query)
        self.assertIn("after:2020/01/15", query)

    def test_gmail_host_uses_x_gm_raw(self) -> None:
        charset, criteria = build_imap_search_criteria(
            ["Statement"],
            date(2021, 6, 1),
            host="imap.gmail.com",
        )
        self.assertIsNone(charset)
        self.assertEqual(criteria[0], "X-GM-RAW")
        self.assertIn("has:attachment", criteria[1])

    def test_generic_imap_since_and_subject(self) -> None:
        charset, criteria = build_imap_search_criteria(
            ["Credit Card Statement"],
            date(2019, 3, 10),
            host="imap.example.com",
        )
        self.assertEqual(charset, "UTF-8")
        self.assertEqual(criteria, ("SINCE", "10-Mar-2019", "SUBJECT", "Credit Card Statement"))

    def test_generic_imap_multiple_subjects_or(self) -> None:
        _charset, criteria = build_imap_search_criteria(
            ["A", "B"],
            None,
            host="imap.example.com",
        )
        self.assertEqual(
            criteria,
            ("OR", "SUBJECT", "A", "SUBJECT", "B"),
        )


if __name__ == "__main__":
    _ = unittest.main()
