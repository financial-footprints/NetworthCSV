"""IndusInd statement balance extraction tests."""

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


def _account(*, variant: str | None = "default") -> ResolvedAccount:
    bank_variants = _APP_CONFIG.banks["indusind"]
    defaults = _resolve_variant_defaults(bank_variants, variant)
    return ResolvedAccount.model_validate(
        {
            "bank": "indusind",
            "variant": variant,
            "account_number": "1234",
            "passwords": ["x"],
            **defaults.model_dump(),
        }
    )


class IndusindStatementBalanceTests(unittest.TestCase):
    def test_previous_balance_next_line(self) -> None:
        text = "Previous Balance\n0.00 DR\nTotal Amount Due\n990.00 CR\n"
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
        self.assertEqual(closing, "-990.00")


if __name__ == "__main__":
    _ = unittest.main()
