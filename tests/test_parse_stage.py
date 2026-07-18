"""Cross-cutting parse-stage output conventions."""

from __future__ import annotations

import unittest

from networthcsv.utils.path import transactions_csv_name


class ParseStageConventionsTests(unittest.TestCase):
    def test_transactions_csv_naming(self) -> None:
        self.assertEqual(transactions_csv_name("2024-05"), "transactions-2024-05.csv")
        self.assertEqual(transactions_csv_name("2025"), "transactions-2025.csv")


if __name__ == "__main__":
    _ = unittest.main()
