"""PNB PDF layout detection tests."""

from __future__ import annotations

import unittest

from helpers import FIXTURES_ROOT
from networthcsv.utils.banks.pnb.default import detect_layout

_FIXTURES = FIXTURES_ROOT / "pnb" / "platinum"


class PnbLayoutDetectionTests(unittest.TestCase):
    def test_detect_v1_classic_fixture(self) -> None:
        text = (_FIXTURES / "2024-03.txt").read_text(encoding="utf-8")
        self.assertEqual(detect_layout(text), "v1")

    def test_detect_v1_same_line_invoice_date_fixture(self) -> None:
        text = (_FIXTURES / "layout_same_line_invoice_date.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(detect_layout(text), "v1")

    def test_detect_v2_marketing_prefix_fixture(self) -> None:
        text = (_FIXTURES / "layout_marketing_prefix.txt").read_text(encoding="utf-8")
        self.assertEqual(detect_layout(text), "v2")

    def test_detect_v1_when_invoice_no_near_top(self) -> None:
        text = (
            "CREDIT CARD (ORIGINAL)\n"
            "Invoice No :\n"
            "2024CC0100456\n"
            "Card No :\n"
            "123456XXXXXX9999\n"
        )
        self.assertEqual(detect_layout(text), "v1")

    def test_detect_v2_when_marketing_precedes_invoice_no(self) -> None:
        text = (
            "Presenting Rupay Platinum and RuPay Millennial Credit Cards\n"
            + ("marketing line\n" * 200)
            + "Invoice No :\n"
            + "2024CC0100999\n"
        )
        self.assertEqual(detect_layout(text), "v2")


if __name__ == "__main__":
    _ = unittest.main()
