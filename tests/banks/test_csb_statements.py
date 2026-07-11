"""CSB statement balance extraction tests."""

from __future__ import annotations

import json
import unittest

from networthcsv.pipeline.metadata.statement_balance import extract_opening_balance
from networthcsv.settings import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ResolvedAccount,
    _resolve_variant_defaults,
)

_APP_CONFIG = AppConfig.from_json(
    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")),
    config_path=DEFAULT_CONFIG_PATH,
)


def _account(*, variant: str | None = "edge") -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks["csb"]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": "csb",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class CsbStatementBalanceTests(unittest.TestCase):
    def test_edge_summary_skips_payment_due_row(self) -> None:
        text = (
            "     Rs. 3,457.05                         01 May  2026\n"
            "     Rs. 500.00                           17/04/2026\n"
            "                     22/03/2026                                         Rs. 0.00\n"
            "                                                                     Rs. 3,457.05\n"
        )
        account = _account()
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        self.assertEqual(opening, "0.00")


if __name__ == "__main__":
    _ = unittest.main()
