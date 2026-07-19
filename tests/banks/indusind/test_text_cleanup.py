"""IndusInd statement text cleanup tests."""

from __future__ import annotations

import unittest

from helpers import credit_card_handler


class IndusindTextCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.handler = credit_card_handler("indusind", "auraedge")

    def test_drops_collapsed_marketing_and_trims_after_rewards(self) -> None:
        raw = (
            "INDUSIND BANK PLATINUM AURA EDGE CREDIT CARD STATEMENT\n"
            "Previous Balance\n"
            "606.64 CR\n"
            "IMPORTANTMESSAGES:            PROMOTIONALMESSAGES:\n"
            "marketing revision notice\n"
            "MARKETINGMESSAGE1:           MARKETINGMESSAGE2:\n"
            "promo offer text\n"
            "Date       TransactionDetails MerchantCategory Amount(in )\n"
            "28/02/2026 SAMPLE MERCHANT US MISCELLANEOUS 1 200.00 DR\n"
            "Total Outstanding\n"
            "404.28 CR\n"
            "Rewards OpeningBalance(Points) PointsEarned PointsRedeemed* ClosingBalance(Points)\n"
            "3            1            0            4\n"
            "PleasedrawyourchequefavouringIndusIndBankCreditCardNo.\n"
            "CREDIT AND CASH WITHDRAWAL LIMITS\n"
            "terms and conditions continue\n"
            "Closest IndusInd Bank ATM Drop Box in your area:\n"
            "more legal text\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("Previous Balance", cleaned)
        self.assertIn("SAMPLE MERCHANT US", cleaned)
        self.assertNotIn("IMPORTANTMESSAGES:", cleaned)
        self.assertNotIn("MARKETINGMESSAGE1:", cleaned)
        self.assertNotIn("promo offer text", cleaned)
        self.assertIn("Rewards OpeningBalance", cleaned)
        self.assertNotIn("CREDIT AND CASH WITHDRAWAL LIMITS", cleaned)
        self.assertNotIn("Closest IndusInd Bank ATM Drop Box", cleaned)
        self.assertNotIn("terms and conditions continue", cleaned)

    def test_interest_rows_before_rewards_survive_trim(self) -> None:
        raw = (
            "INDUSIND BANK PLATINUM AURA EDGE CREDIT CARD STATEMENT\n"
            "Previous Balance\n"
            "606.64 CR\n"
            "28/02/2026 SAMPLE MERCHANT US MISCELLANEOUS 1 200.00 DR\n"
            "28/02/2026 FOREIGN CURRENCY MARKUP FEE     0          2.00 DR\n"
            "28/02/2026 GST @ 18%                       0          .36 DR\n"
            "Total Outstanding\n"
            "404.28 CR\n"
            "Rewards OpeningBalance(Points) PointsEarned PointsRedeemed* ClosingBalance(Points)\n"
            "3            1            0            4\n"
            "CREDIT AND CASH WITHDRAWAL LIMITS\n"
            "terms and conditions continue\n"
        )
        cleaned = self.handler.clean_text(raw)
        self.assertIn("SAMPLE MERCHANT US", cleaned)
        self.assertIn("FOREIGN CURRENCY MARKUP FEE", cleaned)
        self.assertIn("GST @ 18%", cleaned)
        self.assertIn("Rewards OpeningBalance", cleaned)
        self.assertNotIn("CREDIT AND CASH WITHDRAWAL LIMITS", cleaned)
        self.assertNotIn("terms and conditions continue", cleaned)


if __name__ == "__main__":
    _ = unittest.main()
