"""Bank-specific statement parsers."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks.base import StatementParser
from networthcsv.pipeline.parse.banks.stub import StubStatementParser

_DEFAULT_PARSER = StubStatementParser()

# Bank-specific parsers register here as they are implemented.
_BANK_PARSERS: dict[str, StatementParser] = {}


def get_parser(bank: str, variant: str | None = None) -> StatementParser:
    bank_key = bank.strip().lower()
    if variant:
        variant_key = f"{bank_key}/{variant.strip().lower()}"
        parser = _BANK_PARSERS.get(variant_key)
        if parser is not None:
            return parser
    return _BANK_PARSERS.get(bank_key, _DEFAULT_PARSER)
