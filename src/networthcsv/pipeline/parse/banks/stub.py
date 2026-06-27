"""Default statement parser until bank-specific parsers are implemented."""

from __future__ import annotations

import logging

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction

logger = logging.getLogger(__name__)


class StubStatementParser:
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]:
        if not text.strip():
            logger.warning("no text in %s", source_file)
            return []
        logger.debug(
            "no parser implementation for %s/%s; returning no rows for %s",
            account.bank,
            account.variant or "default",
            source_file,
        )
        return []
