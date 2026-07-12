"""IMAP extract helpers."""

from __future__ import annotations

import unittest
from datetime import date

from networthcsv.pipeline.get_statements.imap import (
    build_gmail_raw_query,
    build_imap_search_criteria,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import resolve_account_search_dates


class BuildImapSearchTests(unittest.TestCase):
    def test_gmail_raw_query_with_subjects_and_date(self) -> None:
        query = build_gmail_raw_query(
            ["ICICI Bank Credit Card Statement for the period"],
            date(2020, 1, 15),
        )
        self.assertIn("has:attachment", query)
        self.assertIn(
            'subject:"ICICI Bank Credit Card Statement for the period"', query
        )
        self.assertIn("after:2020/01/15", query)

    def test_gmail_raw_query_with_end_date(self) -> None:
        query = build_gmail_raw_query(
            ["Statement"],
            date(2020, 1, 15),
            date(2024, 4, 1),
        )
        self.assertIn("before:2024/04/01", query)

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
        self.assertEqual(
            criteria, ("SINCE", "10-Mar-2019", "SUBJECT", "Credit Card Statement")
        )

    def test_generic_imap_before_and_since(self) -> None:
        charset, criteria = build_imap_search_criteria(
            ["Credit Card Statement"],
            date(2019, 3, 10),
            host="imap.example.com",
            end_date=date(2024, 4, 1),
        )
        self.assertEqual(charset, "UTF-8")
        self.assertEqual(
            criteria,
            (
                "SINCE",
                "10-Mar-2019",
                "BEFORE",
                "01-Apr-2024",
                "SUBJECT",
                "Credit Card Statement",
            ),
        )

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

    def test_closed_account_imap_before_uses_day_after_closing(self) -> None:
        account = ResolvedAccount.model_validate(
            {
                "bank": "bob",
                "account_number": "1234",
                "passwords": ["x"],
                "mail": {"subjects": ["stmt"]},
                "closing_date": date(2024, 2, 1),
            }
        )
        _start, search_end = resolve_account_search_dates(account, None)
        if search_end is None:
            self.fail("expected closing-date search end")
        self.assertEqual(search_end, date(2024, 2, 2))
        _charset, criteria = build_imap_search_criteria(
            account.mail.subjects,
            date(2024, 1, 1),
            host="imap.example.com",
            end_date=search_end,
        )
        self.assertIn("BEFORE", criteria)
        before_index = criteria.index("BEFORE")
        self.assertEqual(criteria[before_index + 1], "02-Feb-2024")


if __name__ == "__main__":
    _ = unittest.main()
