"""Bank parser registry tests."""

from __future__ import annotations

import unittest

from networthcsv.pipeline.parse.banks import get_parser


class BankParserRegistryTests(unittest.TestCase):
    def test_unknown_bank_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            _ = get_parser("unknown-bank")

    def test_known_banks_are_registered(self) -> None:
        for bank, variant in (
            ("hdfc", "swiggy"),
            ("icici", "amazon"),
            ("idfc", "wow"),
            ("indusind", "auraedge"),
            ("bob", "easy"),
            ("yes", "ace"),
            ("pnb", "platinum"),
            ("federal", "edge"),
            ("csb", "edge"),
        ):
            parser = get_parser(bank, variant)
            self.assertIsNotNone(parser)


if __name__ == "__main__":
    _ = unittest.main()
