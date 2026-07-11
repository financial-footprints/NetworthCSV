"""BoB statement balance extraction tests."""

from __future__ import annotations

import json
import unittest

from networthcsv.pipeline.metadata.statement_balance import (
    extract_closing_balance,
    extract_opening_balance,
)
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


def _account(*, variant: str | None = "easy") -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks["bob"]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": "bob",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class BobStatementBalanceTests(unittest.TestCase):
    def test_account_summary_table(self) -> None:
        text = (
            "Account Summary\n"
            "                                (cid:28)                  / (cid:20)          N   e    w /          (cid:34)\n"
            "Opening Balance Payment/Credits        Closing Balance\n"
            "                               Purchases/Debits\n"
            "    .00        1,001.00      10.00        -991.00\n"
            "Bonus/Reward Points Summary\n"
            "Opening Balance Earned    Redeemed/Expired Closing Balance\n"
            "    0             0            0            0\n"
        )
        account = _account()
        opening = extract_opening_balance(
            text,
            tuple(account.metadata.balances.opening),
        )
        closing = extract_closing_balance(
            text,
            tuple(account.metadata.balances.closing),
        )
        self.assertEqual(opening, "0.00")
        self.assertEqual(closing, "-991.00")


if __name__ == "__main__":
    _ = unittest.main()
