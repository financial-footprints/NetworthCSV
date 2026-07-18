"""Tests for Federal/CSB Edge PDF text enrichment (Cr/Dr + summary labels)."""

from __future__ import annotations

import unittest

from cleanup_support import account as make_account
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.jupiter import (
    annotate_edge_amount_directions,
    annotate_page_text_from_chars,
    inject_edge_summary_labels,
    is_green_amount_color,
    uses_edge_color_extract,
)


class EdgeColorDetectTests(unittest.TestCase):
    def test_green_rgb_is_credit(self) -> None:
        self.assertTrue(is_green_amount_color((0.1, 0.55, 0.2)))
        self.assertTrue(is_green_amount_color((0.0, 0.6, 0.0)))

    def test_black_and_gray_are_not_credit(self) -> None:
        self.assertFalse(is_green_amount_color((0.0, 0.0, 0.0)))
        self.assertFalse(is_green_amount_color(0.2))
        self.assertFalse(is_green_amount_color((0.4, 0.4, 0.4)))

    def test_uses_edge_color_extract_gate(self) -> None:
        self.assertTrue(uses_edge_color_extract("federal", "edge"))
        self.assertTrue(uses_edge_color_extract("csb", "edge"))
        self.assertFalse(uses_edge_color_extract("federal", "signet"))
        self.assertFalse(uses_edge_color_extract("hdfc", "edge"))


class EdgeAnnotateDirectionsTests(unittest.TestCase):
    def test_appends_cr_dr_on_transaction_lines(self) -> None:
        layout = (
            "                    21/12/2020                                           Rs. 0.00\n"
            "                                                                       Rs. 180.00\n"
            "   04 Jan 2021 LIBRARY MEMBERSHIP RENEWAL                                Rs. 180.00\n"
            "   05 Jan 2021 Repayment - Thank You                                      Rs. 830\n"
        )
        # Reading-order flags: summary opening, summary spends, txn debit, txn credit.
        out = annotate_edge_amount_directions(
            layout,
            amount_is_credit=[False, False, False, True],
        )
        self.assertIn("Rs. 180.00 Dr", out)
        self.assertIn("Rs. 830 Cr", out)
        # Summary amounts stay unmarked.
        self.assertIn(
            "21/12/2020                                           Rs. 0.00\n", out
        )
        self.assertNotIn("Rs. 0.00 Dr", out)
        self.assertNotIn("Rs. 0.00 Cr", out)

    def test_does_not_double_annotate(self) -> None:
        layout = "   05 Jan 2021 Repayment - Thank You                                      Rs. 830 Cr\n"
        out = annotate_edge_amount_directions(layout, amount_is_credit=[True])
        self.assertEqual(out.count(" Cr"), 1)

    def test_annotate_from_chars_detects_green_credit(self) -> None:
        layout = (
            "   04 Jan 2021 LIBRARY FEE                                               Rs. 100.00\n"
            "   05 Jan 2021 Repayment - Thank You                                      Rs. 100.00\n"
        )
        black = (0.0, 0.0, 0.0)
        green = (0.05, 0.55, 0.15)
        chars: list[dict[str, object]] = []
        x = 0.0
        for index, amount_color in enumerate((black, green)):
            top = 100.0 + index * 20.0
            for glyph in "Rs.100.00":
                chars.append(
                    {
                        "text": glyph,
                        "x0": x,
                        "x1": x + 5.0,
                        "top": top,
                        "non_stroking_color": amount_color,
                    }
                )
                x += 5.0
            x = 0.0
        out = annotate_page_text_from_chars(layout, chars)
        self.assertIn("Rs. 100.00 Dr", out)
        self.assertIn("Rs. 100.00 Cr", out)


class EdgeSummaryLabelTests(unittest.TestCase):
    def test_injects_labels_on_unlabeled_column(self) -> None:
        text = (
            "    Rs. 500.00                           05/02/2021\n"
            "                    21/12/2020                                           Rs. 0.00\n"
            "                                                                       Rs. 180.00\n"
            "                                                                         Rs. 0.00\n"
            "                                                                         Rs. 3.50\n"
            "                                                                         Rs. 0.60\n"
            "                                                                      Rs. 830.00\n"
            "                                                                         Rs. 0.00\n"
            "                                                                      Rs. -650.25\n"
        )
        labeled = inject_edge_summary_labels(text)
        self.assertIn("Opening Balance  21/12/2020  Rs. 0.00", labeled)
        self.assertIn("Spends  Rs. 180.00", labeled)
        self.assertIn("Cash Advances  Rs. 0.00", labeled)
        self.assertIn("Fees & Charges  Rs. 3.50", labeled)
        self.assertIn("Interest Charges  Rs. 0.60", labeled)
        self.assertIn("Repayments & Refunds  Rs. 830.00", labeled)
        self.assertIn("Paid via points  Rs. 0.00", labeled)
        self.assertIn("Total Amount Due  Rs. -650.25", labeled)

    def test_idempotent_when_already_labeled(self) -> None:
        text = (
            "                    Opening Balance  21/12/2020  Rs. 0.00\n"
            "                    Spends  Rs. 180.00\n"
            "                    Cash Advances  Rs. 0.00\n"
            "                    Fees & Charges  Rs. 3.50\n"
            "                    Interest Charges  Rs. 0.60\n"
            "                    Repayments & Refunds  Rs. 830.00\n"
            "                    Paid via points  Rs. 0.00\n"
            "                    Total Amount Due  Rs. -650.25\n"
        )
        self.assertEqual(inject_edge_summary_labels(text), text)


class EdgeHandlerCleanTextTests(unittest.TestCase):
    def test_federal_edge_clean_injects_labels(self) -> None:
        raw = (
            "                                                             21 DEC 2020 - 20 JAN 2021\n"
            "    Rs. -650.25                          Rs. 0.00\n"
            "                    21/12/2020                                           Rs. 0.00\n"
            "                                                                       Rs. 180.00\n"
            "                                                                         Rs. 0.00\n"
            "                                                                         Rs. 3.50\n"
            "                                                                         Rs. 0.60\n"
            "                                                                      Rs. 830.00\n"
            "                                                                         Rs. 0.00\n"
            "                                                                      Rs. -650.25\n"
            "   04 Jan 2021 LIBRARY MEMBERSHIP RENEWAL                                Rs. 180.00 Dr\n"
            "  ------------------------------------------------ End of Transactions "
            "------------------------------------------------\n"
            "IMPORTANT INFORMATION should be dropped\n"
        )
        handler = get_handler("federal", "edge")
        cleaned = handler.clean_text(raw)
        self.assertIn("Opening Balance", cleaned)
        self.assertIn("Total Amount Due", cleaned)
        self.assertNotIn("IMPORTANT INFORMATION", cleaned)
        self.assertEqual(handler.get_opening_balance(cleaned), "0.00")
        self.assertEqual(handler.get_closing_balance(cleaned), "-650.25")

    def test_csb_edge_balances_with_labels(self) -> None:
        account = make_account(
            bank="csb",
            variant="edge",
            account_number="1234",
            passwords=["x"],
        )
        handler = get_handler(account.bank, account.variant)
        text = (
            "     Rs. 3,457.05                         01 May  2026\n"
            "     Rs. 500.00                           17/04/2026\n"
            "                     22/03/2026                                         Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
            "                                                                        Rs. 0.00\n"
            "                                                                        Rs. 0.00\n"
            "                                                                        Rs. 0.00\n"
            "                                                                        Rs. 0.00\n"
            "                                                                        Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
        )
        cleaned = handler.clean_text(text)
        self.assertIn("Opening Balance", cleaned)
        self.assertEqual(handler.get_opening_balance(cleaned), "0.00")
        self.assertEqual(handler.get_closing_balance(cleaned), "3457.05")


if __name__ == "__main__":
    _ = unittest.main()
