"""Text extraction helper tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from networthcsv.utils.banks.helpers.text import (
    check_text_contains,
    text_contains_present,
    text_not_contains_violated,
    purge_drop_sections,
    sanitize_statement_text,
    trim_by_markers,
)


class TrimByMarkersTests(unittest.TestCase):
    def test_end_marker_only(self) -> None:
        raw = "header\nrow1\n********** End of Statement **********\nfooter"
        result = trim_by_markers(raw, trim_end=["End of Statement"])
        self.assertEqual(
            result,
            "header\nrow1\n********** End of Statement **********",
        )

    def test_start_marker_only(self) -> None:
        raw = "junk\nTransaction Date\nrow1\nrow2"
        result = trim_by_markers(raw, trim_start=["Transaction Date"])
        self.assertEqual(result, "Transaction Date\nrow1\nrow2")

    def test_both_markers(self) -> None:
        raw = "junk\nstart here\nkeep\nend here\nmore junk"
        result = trim_by_markers(raw, trim_start=["start here"], trim_end=["end here"])
        self.assertEqual(result, "start here\nkeep\nend here")

    def test_start_marker_not_found(self) -> None:
        raw = "only content"
        result = trim_by_markers(raw, trim_start=["missing"])
        self.assertEqual(result, "only content")

    def test_end_marker_not_found(self) -> None:
        raw = "only content"
        result = trim_by_markers(raw, trim_end=["missing"])
        self.assertEqual(result, "only content")

    def test_start_after_end_returns_empty(self) -> None:
        raw = "end\nstart"
        result = trim_by_markers(raw, trim_start=["start"], trim_end=["end"])
        self.assertEqual(result, "")

    def test_end_markers_use_latest_match(self) -> None:
        raw = (
            "header\n"
            "txn line\n"
            "Page 1 of 4\n"
            "more txn\n"
            "Page 2 of 4\n"
            "Reward Summary at Card Level\n"
            "footer"
        )
        result = trim_by_markers(
            raw,
            trim_end=["Reward Summary at Card Level", "Page 1 of"],
        )
        self.assertIn("more txn", result)
        self.assertIn("Reward Summary at Card Level", result)
        self.assertNotIn("footer", result)

    def test_end_markers_fallback_when_reward_summary_missing(self) -> None:
        raw = "header\ntxn line\nPage 1 of 5\nPage 2 of 5\nlegal"
        result = trim_by_markers(
            raw,
            trim_end=["Reward Summary at Card Level", "Page 1 of"],
        )
        self.assertIn("Page 1 of 5", result)
        self.assertNotIn("Page 2 of 5", result)
        self.assertNotIn("legal", result)


class PurgeInformationMarkersTests(unittest.TestCase):
    def test_drops_matching_line(self) -> None:
        marker = (
            "*TAD for the month consists of current month purchases, charges, "
            "cash advances and amount of BT/EMI due for the month if any."
        )
        raw = f"keep\n {marker}\nalso keep"
        result = purge_drop_sections(raw, drop_sections=[marker])
        self.assertEqual(result, "keep\nalso keep")

    def test_drops_line_matching_any_marker(self) -> None:
        raw = "row1\nnote about fees\nrow2\nother note"
        result = purge_drop_sections(
            raw,
            drop_sections=["note about fees", "missing"],
        )
        self.assertEqual(result, "row1\nrow2\nother note")

    def test_drops_multiline_pnb_footer(self) -> None:
        marker = (
            "*TAD for the month consists of current month purchases, charges, cash advances "
            "and amount of BT/EMI due for the month if any. Making only the minimum payment "
            "if any month would result in the repayment stretching over subsequent Always get "
            "MORE with months with consequent interest payment on your outstanding balance. "
            "Please examine your statement immediately upon receipt. If no error is reported "
            "within 60 days from the date PNB Credit Cards of statement, the account will be "
            "considered correct. Place of supply : PNB, Credit Card Processing Center, Ground "
            "Floor, C-24, Sec-58, Noida, Uttar Pradesh 201301, State Code : 09 GSTIN No.: "
            "07AAACP0165G3ZP Registered Address : Punjab National Bank, Plot No. 7, East Block "
            "Road, Bhikaji Cama Place, New Delhi, New Delhi, Delhi, 110066 State Code : 07"
        )
        raw = """Total Purchase 1,234.56
 *TAD for the month consists of current month purchases, charges, cash advances and amount of BT/EMI due
  for the month if any.
   Making only the minimum payment if any month would result in the repayment stretching over subsequent Always get MORE with
  months with consequent interest payment on your outstanding balance.
   Please examine your statement immediately upon receipt. If no error is reported within 60 days from the date PNB Credit Cards
  of statement, the account will be considered correct.
   Place of supply : PNB, Credit Card Processing Center, Ground Floor, C-24, Sec-58, Noida, Uttar Pradesh
  201301, State Code : 09
   GSTIN No.: 07AAACP0165G3ZP
   Registered Address : Punjab National Bank, Plot No. 7, East Block Road, Bhikaji Cama Place, New Delhi,
  New Delhi, Delhi, 110066 State Code : 07
********** End of Statement **********"""
        sanitized = sanitize_statement_text(raw)
        result = purge_drop_sections(sanitized, drop_sections=[marker])
        self.assertEqual(
            result,
            "Total Purchase 1,234.56\n********** End of Statement **********",
        )

    def test_drops_multiline_pnb_footer_via_line_block_when_words_differ(self) -> None:
        marker = (
            "*TAD for the month consists of current month purchases, charges, cash advances "
            "and amount of BT/EMI due for the month if any. TOTALLY WRONG MIDDLE SECTION "
            "110066 State Code : 07"
        )
        raw = """Total Purchase 1,234.56
 *TAD for the month consists of current month purchases, charges, cash advances and amount of BT/EMI due
  for the month if any.
   Making only the minimum payment if any month would result in the repayment stretching over subsequent Always get MORE with
  months with consequent interest payment on your outstanding balance.
   Please examine your statement immediately upon receipt. If no error is reported within 60 days from the date PNB Credit Cards
  of statement, the account will be considered correct.
   Place of supply : PNB, Credit Card Processing Center, Ground Floor, C-24, Sec-58, Noida, Uttar Pradesh
  201301, State Code : 09
   GSTIN No.: 07AAACP0165G3ZP
   Registered Address : Punjab National Bank, Plot No. 7, East Block Road, Bhikaji Cama Place, New Delhi,
  New Delhi, Delhi, 110066 State Code : 07
********** End of Statement **********"""
        sanitized = sanitize_statement_text(raw)
        result = purge_drop_sections(sanitized, drop_sections=[marker])
        self.assertEqual(
            result,
            "Total Purchase 1,234.56\n********** End of Statement **********",
        )

    def test_empty_markers_keeps_text(self) -> None:
        raw = "unchanged"
        self.assertEqual(purge_drop_sections(raw, drop_sections=[]), raw)


class SanitizeStatementTextTests(unittest.TestCase):
    def test_tabs_become_spaces_without_collapsing(self) -> None:
        result = sanitize_statement_text("a\t\tb")
        self.assertEqual(result, "a  b")

    def test_regular_spaces_not_collapsed(self) -> None:
        result = sanitize_statement_text("a    b")
        self.assertEqual(result, "a    b")

    def test_mixed_tabs_and_spaces(self) -> None:
        result = sanitize_statement_text("a\t \tb")
        self.assertEqual(result, "a   b")


class TextContainsValidationTests(unittest.TestCase):
    def test_text_contains_present(self) -> None:
        self.assertTrue(text_contains_present("Card ending in 1234", ["1234"]))
        self.assertFalse(text_contains_present("Card ending in 5678", ["1234"]))
        self.assertTrue(
            text_contains_present("Card ending in XXXX5678", ["1234", "XXXX5678"])
        )
        self.assertFalse(
            text_contains_present("Card ending in 9999", ["1234", "XXXX5678"])
        )

    def test_text_not_contains_violated(self) -> None:
        self.assertTrue(
            text_not_contains_violated("Card for Anotherthing", ["Anotherthing"])
        )
        self.assertFalse(
            text_not_contains_violated("Card ending in 5678", ["Anotherthing"])
        )
        self.assertFalse(text_not_contains_violated("any text", []))
        self.assertTrue(
            text_not_contains_violated(
                "ANNUAL  SPEND  SUMMARY for FY",
                ["ANNUAL SPEND SUMMARY"],
            )
        )

    @patch("networthcsv.utils.banks.helpers.text.logger.debug")
    def test_text_contains_found(self, mock_debug: MagicMock) -> None:
        result = check_text_contains(
            "Card ending in 1234",
            text_contains=["1234"],
            source_file="2024-01.pdf",
            account_label="pnb/platinum",
        )
        self.assertTrue(result)
        mock_debug.assert_not_called()

    @patch("networthcsv.utils.banks.helpers.text.logger.debug")
    def test_text_contains_missing(self, mock_debug: MagicMock) -> None:
        result = check_text_contains(
            "Card ending in 5678",
            text_contains=["1234"],
            source_file="2024-01.pdf",
            account_label="pnb/platinum",
        )
        self.assertFalse(result)
        mock_debug.assert_called_once_with(
            "ignored %s for %s: text_contains %r not found",
            "2024-01.pdf",
            "pnb/platinum",
            ["1234"],
        )


if __name__ == "__main__":
    _ = unittest.main()
