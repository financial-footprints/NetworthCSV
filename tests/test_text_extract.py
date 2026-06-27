"""Text extraction helper tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from networthcsv.pipeline.cleanup.statement_text import (
    check_file_marker,
    file_marker_present,
    purge_information_markers,
    sanitize_statement_text,
    trim_by_markers,
)


class TrimByMarkersTests(unittest.TestCase):
    def test_end_marker_only(self) -> None:
        raw = "header\nrow1\n********** End of Statement **********\nfooter"
        result = trim_by_markers(raw, end_marker="End of Statement")
        self.assertEqual(
            result,
            "header\nrow1\n********** End of Statement **********",
        )

    def test_start_marker_only(self) -> None:
        raw = "junk\nTransaction Date\nrow1\nrow2"
        result = trim_by_markers(raw, start_marker="Transaction Date")
        self.assertEqual(result, "Transaction Date\nrow1\nrow2")

    def test_both_markers(self) -> None:
        raw = "junk\nstart here\nkeep\nend here\nmore junk"
        result = trim_by_markers(raw, start_marker="start here", end_marker="end here")
        self.assertEqual(result, "start here\nkeep\nend here")

    def test_start_marker_not_found(self) -> None:
        raw = "only content"
        result = trim_by_markers(raw, start_marker="missing")
        self.assertEqual(result, "only content")

    def test_end_marker_not_found(self) -> None:
        raw = "only content"
        result = trim_by_markers(raw, end_marker="missing")
        self.assertEqual(result, "only content")

    def test_start_after_end_returns_empty(self) -> None:
        raw = "end\nstart"
        result = trim_by_markers(raw, start_marker="start", end_marker="end")
        self.assertEqual(result, "")


class PurgeInformationMarkersTests(unittest.TestCase):
    def test_drops_matching_line(self) -> None:
        marker = (
            "*TAD for the month consists of current month purchases, charges, "
            "cash advances and amount of BT/EMI due for the month if any."
        )
        raw = f"keep\n {marker}\nalso keep"
        result = purge_information_markers(raw, information_markers=[marker])
        self.assertEqual(result, "keep\nalso keep")

    def test_drops_line_matching_any_marker(self) -> None:
        raw = "row1\nnote about fees\nrow2\nother note"
        result = purge_information_markers(
            raw,
            information_markers=["note about fees", "missing"],
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
        result = purge_information_markers(sanitized, information_markers=[marker])
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
        result = purge_information_markers(sanitized, information_markers=[marker])
        self.assertEqual(
            result,
            "Total Purchase 1,234.56\n********** End of Statement **********",
        )

    def test_empty_markers_keeps_text(self) -> None:
        raw = "unchanged"
        self.assertEqual(purge_information_markers(raw, information_markers=[]), raw)


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


class FileMarkerValidationTests(unittest.TestCase):
    def test_file_marker_present(self) -> None:
        self.assertTrue(file_marker_present("Card ending in 1234", "1234"))
        self.assertFalse(file_marker_present("Card ending in 5678", "1234"))

    @patch("networthcsv.pipeline.cleanup.statement_text.logger.debug")
    def test_file_marker_found(self, mock_debug: MagicMock) -> None:
        result = check_file_marker(
            "Card ending in 1234",
            file_marker="1234",
            source_file="2024-01.pdf",
            account_label="pnb/platinum",
        )
        self.assertTrue(result)
        mock_debug.assert_not_called()

    @patch("networthcsv.pipeline.cleanup.statement_text.logger.debug")
    def test_file_marker_missing(self, mock_debug: MagicMock) -> None:
        result = check_file_marker(
            "Card ending in 5678",
            file_marker="1234",
            source_file="2024-01.pdf",
            account_label="pnb/platinum",
        )
        self.assertFalse(result)
        mock_debug.assert_called_once_with(
            "ignored %s for %s: file marker %r not found",
            "2024-01.pdf",
            "pnb/platinum",
            "1234",
        )


if __name__ == "__main__":
    _ = unittest.main()
