"""Statement parser protocol."""

from __future__ import annotations

from typing import Protocol

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


class StatementParser(Protocol):
    def parse(
        self,
        text: str,
        *,
        account: ResolvedAccount,
        source_file: str,
    ) -> list[Transaction]: ...
